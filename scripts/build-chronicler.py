#!/usr/bin/env python3
"""在当前原生平台构建 sealed Chronicler standalone 发行包。"""
import argparse
import base64
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_ROOT = ROOT / "build" / "chronicler"
sys.path.insert(0, str(ROOT))


def _run(args: list[str], cwd: Path = ROOT) -> None:
    completed = subprocess.run(args, cwd=str(cwd))
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _copy_source(stage: Path) -> Path:
    target = stage / "chronicler"
    shutil.copytree(ROOT / "chronicler", target, ignore=shutil.ignore_patterns(
        ".venv*", "components", "prompts", "scripts", "tests", "__pycache__", "*.pyc"))
    return target


def _write_sealed_profile(package: Path, key: bytes) -> None:
    encoded = base64.urlsafe_b64encode(key).decode("ascii")
    (package / "app" / "_sealed_profile.py").write_text(
        "# Generated during sealed build; never commit this file.\n"
        f"PROMPT_KEY_B64 = {encoded!r}\n", encoding="utf-8", newline="\n")


def _platform_tag() -> str:
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(
        platform.system(), platform.system().lower())
    machine = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    return f"{system}-{machine}"


def _verify_bundle(path: Path, key: bytes, expected_count: int) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from chronicler.app.prompt_catalog import BUNDLE_AAD
    bundle = json.loads(path.read_text(encoding="utf-8"))
    payload = AESGCM(key).decrypt(base64.b64decode(bundle["nonce"]),
                                  base64.b64decode(bundle["ciphertext"]), BUNDLE_AAD)
    if len(json.loads(payload)["prompts"]) != expected_count:
        raise RuntimeError("Prompt bundle 往返校验失败")


def _verify_release(release: Path, prompt_contents: list[str], bundle_only: bool) -> None:
    forbidden = []
    for path in release.rglob("*"):
        relative = path.relative_to(release)
        if path.is_dir() and relative.parts and relative.parts[0] == "components":
            forbidden.append(str(relative))
        elif path.is_file() and (path.suffix == ".py" or
                                 ("prompt" in path.name.lower() and path.suffix in (".yaml", ".yml"))):
            forbidden.append(str(relative))
    if forbidden:
        raise RuntimeError(f"sealed 发行包含禁止文件：{forbidden[:10]}")
    needles = [content[:160].encode("utf-8") for content in prompt_contents]
    for path in release.rglob("*"):
        if not path.is_file() or path.name == "prompts.bundle":
            continue
        data = path.read_bytes()
        if any(needle in data for needle in needles):
            raise RuntimeError(f"sealed 发行包含 Prompt 特征明文：{path.relative_to(release)}")
    executable = release / ("chronicler.exe" if platform.system() == "Windows" else "chronicler")
    if not bundle_only and not executable.is_file():
        raise RuntimeError(f"sealed 发行缺少可执行文件：{executable}")


def build(version: str, output_root: Path, bundle_only: bool = False) -> Path:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", version):
        raise SystemExit("--version 必须是 SemVer")
    if not bundle_only and sys.version_info[:2] != (3, 11):
        raise SystemExit("sealed Nuitka 构建当前固定使用 CPython 3.11；其它版本尚未通过 FastAPI/Pydantic 黑盒验证")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    from chronicler.app.prompt_catalog import PromptCatalog, build_bundle

    definitions = PromptCatalog().list()
    release = output_root / f"chronicler-{version}-{_platform_tag()}"
    if release.exists():
        shutil.rmtree(release)
    release.mkdir(parents=True)
    key = AESGCM.generate_key(bit_length=256)

    with tempfile.TemporaryDirectory(dir=BUILD_ROOT) as temp:
        stage = Path(temp)
        package = _copy_source(stage)
        _write_sealed_profile(package, key)
        resources = release / "resources"
        resources.mkdir()
        bundle_info = build_bundle(
            ROOT / "chronicler" / "prompts", resources / "prompts.bundle", key,
            (ROOT / "chronicler" / "assets" / "prompts",))
        _verify_bundle(resources / "prompts.bundle", key, len(definitions))
        shutil.copytree(ROOT / "chronicler" / "app" / "static", resources / "static")
        shutil.copytree(ROOT / "chronicler" / "config", resources / "config")
        shutil.copytree(ROOT / "chronicler" / "assets", resources / "assets",
                        ignore=shutil.ignore_patterns("prompts"))
        shutil.copy2(ROOT / ".env.example", release / ".env.example")
        shutil.copy2(ROOT / "LICENSE", release / "LICENSE")
        shutil.copy2(ROOT / "scripts" / "install-chronicler.ps1", release / "install.ps1")
        shutil.copy2(ROOT / "scripts" / "install-chronicler.sh", release / "install.sh")

        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=str(ROOT),
                        capture_output=True, text=True).stdout.strip())
        manifest = {"product": "Chronicler", "version": version, "profile": "sealed",
                    "platform": _platform_tag(), "source_commit": commit,
                "source_dirty": dirty,
                    "build_python": platform.python_version(),
                    "prompt_bundle": bundle_info,
                    "prompts": [{"name": item.name, "version": item.version,
                                 "content_hash": item.content_hash} for item in definitions],
                    "components_included": False,
                    "components_path": "components",
                    "bundle_only": bundle_only}
        (release / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        if bundle_only:
            _verify_release(release, [item.content for item in definitions], True)
            return release

        entry = stage / "chronicler_entry.py"
        entry.write_text("from chronicler.__main__ import main\nmain()\n",
                         encoding="utf-8", newline="\n")
        nuitka_output = stage / "nuitka"
        report = BUILD_ROOT / f"compilation-report-{_platform_tag()}.xml"
        _run([sys.executable, "-m", "nuitka", "--mode=standalone", "--deployment",
              "--python-flag=isolated", "--jobs=1", "--include-package=chronicler",
              "--nofollow-import-to=chronicler.tests",
              "--noinclude-pytest-mode=nofollow", f"--output-dir={nuitka_output}",
              "--output-filename=chronicler", f"--report={report}", str(entry)], cwd=stage)
        dist_dirs = list(nuitka_output.glob("*.dist"))
        if len(dist_dirs) != 1:
            raise RuntimeError(f"无法定位 Nuitka standalone 目录：{dist_dirs}")
        for item in dist_dirs[0].iterdir():
            destination = release / item.name
            shutil.move(str(item), str(destination))
            _verify_release(release, [item.content for item in definitions], False)
    return release


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--bundle-only", action="store_true",
                        help="只验证发行资源与加密 bundle，不调用 Nuitka")
    args = parser.parse_args()
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    release = build(args.version, args.output.resolve(), args.bundle_only)
    print(release)


if __name__ == "__main__":
    main()

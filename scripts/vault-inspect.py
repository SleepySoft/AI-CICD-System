#!/usr/bin/env python3
"""vault-inspect：Chronicler 秘密库导出包的本地浏览与验证工具（ADR-0041/0042）。

不依赖 Chronicler 运行。list 无需密钥（manifest 明文）；verify/show/extract 需要主密钥。
解密优先用 pyrage（pip install pyrage），退回系统 age/rage CLI。

用法：
  python scripts/vault-inspect.py list    <export.tar>
  python scripts/vault-inspect.py verify  <export.tar> [--key secrets/master.key]
  python scripts/vault-inspect.py show    <export.tar> --key secrets/master.key --name <scope/name> [--out <文件>]
  python scripts/vault-inspect.py extract <export.tar> --key secrets/master.key -d <目录>
"""
import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path


def _fail(msg: str, code: int = 1):
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(code)


def _load_manifest(export: Path) -> tuple[dict, bytes]:
    if not export.exists():
        _fail(f"文件不存在：{export}")
    with tarfile.open(export) as tar:
        try:
            manifest = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
            payload = tar.extractfile("payload.age").read()
        except KeyError as e:
            _fail(f"导出包缺少成员：{e}")
    if manifest.get("format") != "chronicler-vault-export":
        _fail("不是 Chronicler 秘密库导出包（format 不匹配）")
    return manifest, payload


def _load_identity(key_path: Path) -> str:
    if not key_path.exists():
        _fail(f"密钥文件不存在：{key_path}")
    for line in key_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("AGE-SECRET-KEY-"):
            return line
    _fail(f"{key_path} 中找不到 AGE-SECRET-KEY 行")


def _decrypt(blob: bytes, key_path: Path) -> bytes:
    identity = _load_identity(key_path)
    try:
        import pyrage
        from pyrage import x25519
        return pyrage.decrypt(blob, [x25519.Identity.from_str(identity)])
    except ImportError:
        exe = shutil.which("age") or shutil.which("rage")
        if not exe:
            _fail("解密需要 pyrage（pip install pyrage）或 PATH 上的 age/rage")
        result = subprocess.run([exe, "-d", "-i", str(key_path)], input=blob,
                                capture_output=True)
        if result.returncode != 0:
            _fail("解密失败：密钥不匹配或文件损坏")
        return result.stdout
    except Exception:
        _fail("解密失败：密钥不匹配或文件损坏")


def _fmt_time(ts) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "-"


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n / 1024:.1f}{unit}".replace(".0", "")
        n /= 1024


def cmd_list(args):
    manifest, _ = _load_manifest(Path(args.export))
    print(f"导出时间：{_fmt_time(manifest['exported_at'])}  接收者：{manifest['recipient']}")
    print(f"秘密条数：{manifest['count']}  负载 sha256：{manifest['payload_sha256'][:16]}…\n")
    print(f"{'SCOPE/名称':<32} {'类型':<6} {'秘密类型':<14} {'属主':<12} {'过期时间':<20} {'大小':<8} 摘要")
    for it in manifest["items"]:
        label = f"{it['scope']}/{it['name']}"
        print(f"{label:<32} {it['kind']:<6} {it['secret_type']:<14} {(it['owner'] or '-'):<12} "
              f"{_fmt_time(it['expires_at']):<20} {_fmt_size(it['size']):<8} {it['sha256'][:12]}…")
    print("\n（清单为明文，无需密钥；秘密值在 payload.age 中，需主密钥解密）")


def _verify_payload(manifest: dict, payload_plain: bytes) -> bool:
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(payload_plain)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                entries[member.name] = tar.extractfile(member).read()
    ok = True
    for it in manifest["items"]:
        data = entries.get(it["path"])
        if data is None:
            print(f"FAIL  {it['path']}  负载中缺失")
            ok = False
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest != it["sha256"] or len(data) != it["size"]:
            print(f"FAIL  {it['path']}  摘要不一致（可能已损坏）")
            ok = False
        else:
            print(f"OK    {it['path']}")
    extra = set(entries) - {it["path"] for it in manifest["items"]}
    for name in extra:
        print(f"WARN  {name}  负载中存在但清单未登记")
        ok = False
    return ok


def cmd_verify(args):
    manifest, payload = _load_manifest(Path(args.export))
    actual = hashlib.sha256(payload).hexdigest()
    if actual != manifest["payload_sha256"]:
        _fail("payload.age 摘要与清单不一致：导出包可能已被篡改")
    print(f"payload.age 摘要一致（{actual[:16]}…）")
    if not args.key:
        print("未提供 --key：仅校验包完整性，未解密逐条验证")
        return
    plain = _decrypt(payload, Path(args.key))
    if _verify_payload(manifest, plain):
        print(f"\n全部 {manifest['count']} 条秘密完整性验证通过")
    else:
        _fail("存在不一致项")


def _decrypt_entries(args) -> tuple[dict, dict]:
    manifest, payload = _load_manifest(Path(args.export))
    plain = _decrypt(payload, Path(args.key))
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(plain)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                entries[member.name] = tar.extractfile(member).read()
    return manifest, entries


def cmd_show(args):
    manifest, entries = _decrypt_entries(args)
    target = None
    for it in manifest["items"]:
        if f"{it['scope']}/{it['name']}" == args.name:
            target = it
            break
    if not target:
        _fail(f"找不到秘密：{args.name}（用 list 查看全部）")
    data = entries[target["path"]]
    if target["kind"] == "text" and not args.out:
        sys.stdout.write(data.decode("utf-8"))
        if not data.endswith(b"\n"):
            print()
    else:
        out = Path(args.out or target["filename"] or target["name"])
        out.write_bytes(data)
        print(f"已写出：{out}（{len(data)} 字节）")


def cmd_extract(args):
    _, entries = _decrypt_entries(args)
    dest = Path(args.dir)
    dest.mkdir(parents=True, exist_ok=True)
    for name, data in entries.items():
        if ".." in Path(name).parts:
            _fail(f"非法路径：{name}")
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    print(f"已解出 {len(entries)} 个文件到 {dest}（注意及时清理或加密保管）")


def main():
    # Windows 下管道默认 GBK，强制 UTF-8 输出（AGENTS.md 已知坑）
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(description="Chronicler 秘密库导出包浏览/验证工具")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("list", "verify", "show", "extract"):
        p = sub.add_parser(name)
        p.add_argument("export", help="导出包（vault-export-*.tar）")
        if name != "list":
            p.add_argument("--key", help="主密钥文件（secrets/master.key）")
        if name == "show":
            p.add_argument("--name", required=True, help="scope/name")
            p.add_argument("--out", help="文件型秘密的输出路径")
        if name == "extract":
            p.add_argument("-d", "--dir", required=True, help="解出目录")
    args = parser.parse_args()
    {"list": cmd_list, "verify": cmd_verify, "show": cmd_show, "extract": cmd_extract}[args.cmd](args)


if __name__ == "__main__":
    main()

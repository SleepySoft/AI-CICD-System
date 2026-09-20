"""结构化 Prompt Catalog：source YAML / sealed AES-GCM bundle / 用户覆盖。"""
import base64
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

from .config import Cfg
from .runtime import PROFILE

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
BUNDLE_AAD = b"chronicler-prompt-bundle-v1"


@dataclass(frozen=True)
class PromptDefinition:
    name: str
    version: str
    title: str
    schema_version: int
    variables: tuple[str, ...]
    output_kind: str
    content: str
    content_hash: str
    builtin: bool
    overridden: bool

    def metadata(self) -> dict:
        return {"name": self.name, "version": self.version, "title": self.title,
                "schema_version": self.schema_version, "variables": list(self.variables),
                "output_kind": self.output_kind, "content_hash": self.content_hash,
                "builtin": self.builtin, "overridden": self.overridden,
                "disclosure": ("full" if (not self.builtin or PROFILE.prompt_disclosure == "full")
                               else "metadata-only")}


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse(data: dict, *, builtin: bool, overridden: bool, source: str) -> PromptDefinition:
    if not isinstance(data, dict):
        raise RuntimeError(f"Prompt 不是对象：{source}")
    name = str(data.get("name", "")).strip()
    version = str(data.get("version", "")).strip()
    title = str(data.get("title", "")).strip()
    content = str(data.get("content", "")).strip()
    variables = data.get("variables") or []
    output = data.get("output") or {}
    if not _NAME_RE.fullmatch(name):
        raise RuntimeError(f"Prompt name 非法：{source}")
    if not _VERSION_RE.fullmatch(version):
        raise RuntimeError(f"Prompt version 必须是 SemVer：{source}")
    if not title or not content:
        raise RuntimeError(f"Prompt title/content 不能为空：{source}")
    schema_version = int(data.get("schema_version", 0))
    if schema_version not in (1, 2):
        raise RuntimeError(f"不支持的 Prompt schema_version：{source}")
    if not isinstance(variables, list) or not all(isinstance(item, str) for item in variables):
        raise RuntimeError(f"Prompt variables 必须是字符串数组：{source}")
    declared = set(variables)
    used = set(re.findall(r"\{\{([a-z_]+)\}\}", content))
    if used != declared:
        raise RuntimeError(f"Prompt variables 与正文不一致：{source} declared={sorted(declared)} used={sorted(used)}")
    return PromptDefinition(name=name, version=version, title=title, schema_version=schema_version,
                            variables=tuple(variables), output_kind=str(output.get("kind", "report")),
                            content=content, content_hash=_content_hash(content),
                            builtin=builtin, overridden=overridden)


def _load_yaml(path: Path, *, builtin: bool, overridden: bool) -> PromptDefinition:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Prompt 不是对象：{path}")
    content_file = data.get("content_file")
    if content_file:
        body_path = path.parent / str(content_file)
        if not body_path.is_file():
            raise RuntimeError(f"Prompt body 文件不存在：{body_path}")
        if "content" in data:
            raise RuntimeError(f"Prompt metadata 不应内嵌 content：{path}")
        if Path(str(content_file)).name != str(content_file):
            raise RuntimeError(f"Prompt body 必须与 metadata 同目录：{path}")
        data["content"] = body_path.read_text(encoding="utf-8")
    definition = _parse(data, builtin=builtin,
                        overridden=overridden, source=str(path))
    if content_file and definition.name != path.stem:
        raise RuntimeError(f"Prompt name 与 metadata 文件名不一致：{path}")
    return definition


def build_bundle(source_dir: Path, output: Path, key: bytes,
                 extra_source_dirs: tuple[Path, ...] = ()) -> dict:
    prompts = []
    seen: set[str] = set()
    for source_dir in (source_dir, *extra_source_dirs):
        for path in sorted(source_dir.glob("*.yaml")):
            definition = _load_yaml(path, builtin=True, overridden=False)
            if definition.name in seen:
                raise RuntimeError(f"Prompt name 重复：{definition.name}")
            seen.add(definition.name)
            prompts.append({"name": definition.name, "version": definition.version,
                            "title": definition.title, "schema_version": definition.schema_version,
                            "variables": list(definition.variables),
                            "output": {"kind": definition.output_kind}, "content": definition.content})
    if not prompts:
        raise RuntimeError(f"Prompt 目录为空：{source_dir}")
    plaintext = json.dumps({"schema_version": 1, "prompts": prompts},
                           ensure_ascii=False, sort_keys=True).encode("utf-8")
    nonce = __import__("os").urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, BUNDLE_AAD)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schema_version": 1,
                                  "nonce": base64.b64encode(nonce).decode("ascii"),
                                  "ciphertext": base64.b64encode(ciphertext).decode("ascii")},
                                 separators=(",", ":")), encoding="utf-8", newline="\n")
    return {"count": len(prompts), "bundle_hash": _content_hash(output.read_text(encoding="utf-8"))}


class PromptCatalog:
    def __init__(self):
        self._builtins: dict[str, PromptDefinition] | None = None

    def _load_builtins(self) -> dict[str, PromptDefinition]:
        if PROFILE.sealed and self._builtins is not None:
            return self._builtins
        if PROFILE.sealed:
            bundle = json.loads((Cfg.RESOURCE_DIR / "prompts.bundle").read_text(encoding="utf-8"))
            nonce = base64.b64decode(bundle["nonce"])
            ciphertext = base64.b64decode(bundle["ciphertext"])
            payload = json.loads(AESGCM(PROFILE.prompt_key).decrypt(nonce, ciphertext, BUNDLE_AAD))
            definitions = [_parse(item, builtin=True, overridden=False, source="prompts.bundle")
                           for item in payload["prompts"]]
        else:
            definitions = [_load_yaml(path, builtin=True, overridden=False)
                           for path in sorted(Cfg.PROMPTS_DIR.glob("*.yaml"))]
            assets_dir = Cfg.asset_prompts_dir()
            if assets_dir.is_dir():
                definitions.extend(_load_yaml(path, builtin=True, overridden=False)
                                   for path in sorted(assets_dir.glob("*.yaml")))
        loaded = {item.name: item for item in definitions}
        if not PROFILE.sealed and len(loaded) != len(definitions):
            raise RuntimeError("Prompt name 重复")
        if PROFILE.sealed:
            self._builtins = loaded
        return loaded

    def list(self) -> list[PromptDefinition]:
        self._migrate_legacy_overrides()
        names = set(self._load_builtins())
        names.update(path.stem for path in Cfg.prompts_override_dir().glob("*.yaml"))
        return [self.resolve(name) for name in sorted(names)]

    def resolve(self, name: str) -> PromptDefinition:
        self._migrate_legacy_overrides()
        override = Cfg.prompts_override_dir() / f"{name}.yaml"
        if override.is_file():
            item = _load_yaml(override, builtin=False, overridden=True)
            if item.name != name:
                raise RuntimeError(f"覆盖 Prompt name 与文件名不一致：{override}")
            return item
        item = self._load_builtins().get(name)
        if not item:
            raise HTTPException(status_code=404, detail=f"未知 Prompt：{name}")
        return item

    def _migrate_legacy_overrides(self) -> None:
        if PROFILE.sealed:
            return
        for path in Cfg.prompts_override_dir().glob("*.md"):
            target = path.with_suffix(".yaml")
            builtin = self._load_builtins().get(path.stem)
            if target.exists() or not builtin:
                continue
            data = {"schema_version": 1, "name": builtin.name, "version": "0.0.0+legacy",
                    "title": builtin.title, "variables": list(builtin.variables),
                    "output": {"kind": builtin.output_kind},
                    "content": path.read_text(encoding="utf-8")}
            _parse(data, builtin=False, overridden=True, source=str(path))
            target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                              encoding="utf-8", newline="\n")
            path.rename(path.with_suffix(".md.migrated"))

    def content_for_display(self, name: str) -> str | None:
        item = self.resolve(name)
        if item.builtin and PROFILE.prompt_disclosure != "full":
            return None
        return item.content

    def save_override(self, name: str, version: str, content: str) -> PromptDefinition:
        builtin = self._load_builtins().get(name)
        if not builtin:
            raise HTTPException(status_code=404, detail=f"未知 Prompt：{name}")
        data = {"schema_version": 1, "name": name, "version": version,
                "title": builtin.title, "variables": list(builtin.variables),
                "output": {"kind": builtin.output_kind}, "content": content}
        item = _parse(data, builtin=False, overridden=True, source=f"override:{name}")
        current = self.resolve(name)
        if current.version == item.version and current.content_hash != item.content_hash:
            raise HTTPException(status_code=409,
                                detail="Prompt 内容已变化，必须提升 version；同一 name+version 不得对应不同内容")
        path = Cfg.prompts_override_dir() / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                        encoding="utf-8", newline="\n")
        return item

    def delete_override(self, name: str) -> None:
        path = Cfg.prompts_override_dir() / f"{name}.yaml"
        if path.is_file():
            path.unlink()


catalog = PromptCatalog()

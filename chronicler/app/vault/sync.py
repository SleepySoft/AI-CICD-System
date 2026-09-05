"""组件秘密与 .env 的对接（docs/how/secrets-vault.md）。

vault 对 .env 只读：双写方向为 .env → vault；漂移检测只读比对 sha256。
核心不含组件知识：字段元数据（secret_type/rotation_risk/help）全部来自组件 setup.yaml 自述。
"""
import hashlib
from pathlib import Path

from ..db import audit
from ..db import init as db_init
from ..runtime import PROFILE
from . import store

# 全局秘密键（比 config_store.GLOBAL_SECRET_KEYS 多收 OIDC 客户端密钥——它也是秘密）
GLOBAL_SECRETS = {
    "CHRONICLER_SECRET": {"secret_type": "encryption-key", "rotation_risk": "critical",
                          "summary": "Chronicler 会话签名密钥"},
    "CHRONICLER_OIDC_SECRET": {"secret_type": "client-secret", "rotation_risk": "coordinated",
                               "summary": "Chronicler OIDC 客户端密钥"},
}
INFRA_SCOPE = "infra"


def secret_field_map(components: dict) -> dict:
    """env key → vault 元数据（scope=组件名，类型/风险/说明沿用 setup.yaml 自述）。"""
    result = {}
    for comp_name, entry in components.items():
        for field in entry.get("component", {}).get("fields", []):
            if field.get("kind") == "secret":
                result[field["key"]] = {"scope": comp_name,
                                        "secret_type": field["secret_type"],
                                        "rotation_risk": field["rotation_risk"],
                                        "summary": field.get("help", "")}
    for key, meta in GLOBAL_SECRETS.items():
        result.setdefault(key, {"scope": INFRA_SCOPE, **meta})
    return result


def sync_env_secrets(values: dict, components: dict, actor: str = "setup") -> int:
    """persist 双写：把本次写入 .env 的秘密键同步进 vault。返回变化条数。"""
    fmap = secret_field_map(components)
    targets = {key: value for key, value in values.items()
               if key in fmap and value and not key.startswith("INIT_ADMIN_")}
    if not targets:
        return 0
    db_init()  # bootstrap 模式下幂等补表（normal 模式为 no-op）
    changed = 0
    for key, value in sorted(targets.items()):
        outcome = store.upsert(kind="text", name=key, scope=fmap[key]["scope"],
                               plain=str(value).encode("utf-8"), actor=actor,
                               secret_type=fmap[key]["secret_type"],
                               rotation_risk=fmap[key]["rotation_risk"],
                               summary=fmap[key]["summary"], owner=fmap[key]["scope"])
        if outcome != "unchanged":
            changed += 1
    if changed:
        audit(actor, "vault.sync", "", f"count={changed}")
    return changed


def read_env_secrets(components: dict) -> dict:
    """只读解析 .env 中已配置的组件秘密（跳过占位值）。"""
    path = PROFILE.install_root / ".env"
    if not path.is_file():
        return {}
    declared = secret_field_map(components)
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#") and "=" in clean:
            key, _, value = clean.partition("=")
            key, value = key.strip(), value.strip()
            if key in declared and value and "change_me" not in value.lower():
                found[key] = value
    return found


def import_env(components: dict, actor: str, force: bool = False) -> dict:
    """把 .env 中已配置的组件秘密导入 vault（老系统接管）。冲突默认不覆盖。"""
    fmap = secret_field_map(components)
    env_values = read_env_secrets(components)
    imported, skipped, conflicts = 0, 0, []
    for key, value in sorted(env_values.items()):
        meta = fmap[key]
        existing = store.find(meta["scope"], key)
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        if existing and existing["sha256"] == digest:
            skipped += 1
            continue
        if existing and not force:
            conflicts.append(key)
            continue
        store.upsert(kind="text", name=key, scope=meta["scope"], plain=value.encode("utf-8"),
                     actor=actor, secret_type=meta["secret_type"],
                     rotation_risk=meta["rotation_risk"], summary=meta["summary"],
                     owner=meta["scope"])
        imported += 1
    audit(actor, "vault.import_env", "",
          f"imported={imported} skipped={skipped} conflicts={len(conflicts)} force={force}")
    return {"imported": imported, "skipped": skipped, "conflicts": conflicts,
            "env_secret_count": len(env_values)}


def env_status(components: dict) -> dict:
    """漂移检测（只读）：.env 与 vault 的双向比对，基于明文 sha256，不泄露值。"""
    fmap = secret_field_map(components)
    env_values = read_env_secrets(components)
    missing_in_vault, drifted = [], []
    for key, value in sorted(env_values.items()):
        row = store.find(fmap[key]["scope"], key)
        if not row:
            missing_in_vault.append(key)
        elif row["sha256"] != hashlib.sha256(value.encode("utf-8")).hexdigest():
            drifted.append(f"{fmap[key]['scope']}/{key}")
    managed_keys = {(meta["scope"], key) for key, meta in fmap.items()}
    missing_in_env = [f"{row['scope']}/{row['name']}" for row in store.all_rows()
                      if (row["scope"], row["name"]) in managed_keys
                      and row["name"] not in env_values]
    return {"missing_in_vault": missing_in_vault, "drifted": drifted,
            "missing_in_env": missing_in_env,
            "managed": [f"{meta['scope']}/{key}" for key, meta in sorted(fmap.items())]}

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

VAULT_PREFIX = "VAULT:"  # 糊化占位引用（ADR-0045）：KEY=VAULT:<scope>/<KEY>

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
               if (key in fmap and value and not key.startswith("INIT_ADMIN_")
                   and "change_me" not in str(value).lower())}
    if not targets:
        return 0
    from ..db import close as db_close
    try:
        db_init()  # bootstrap 模式下幂等补表（normal 模式为 no-op）
        changed = 0
        for key, value in sorted(targets.items()):
            outcome = store.upsert(kind="text", name=key, scope=fmap[key]["scope"],
                                   plain=str(value).encode("utf-8"), actor=actor,
                                   mark_pending=False,  # 存量收养：值本来就是运行事实
                                   secret_type=fmap[key]["secret_type"],
                                   rotation_risk=fmap[key]["rotation_risk"],
                                   summary=fmap[key]["summary"], owner=fmap[key]["scope"])
            if outcome != "unchanged":
                changed += 1
        if changed:
            audit(actor, "vault.sync", "", f"count={changed}")
        return changed
    finally:
        db_close()  # 双写可能在任意线程（bootstrap 请求线程）执行，用完即关防 Windows 文件锁


def read_env_secrets(components: dict) -> dict:
    """只读解析 .env 中已配置的组件秘密（跳过占位值与糊化引用）。"""
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
            if (key in declared and value and "change_me" not in value.lower()
                    and not value.startswith(VAULT_PREFIX)):
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
                     actor=actor, mark_pending=False, secret_type=meta["secret_type"],
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


# ---------- 糊化与使用时渲染（ADR-0045） ----------

def mask_ref(scope: str, key: str) -> str:
    return f"{VAULT_PREFIX}{scope}/{key}"


def mask_env_text(text: str, components: dict) -> str:
    """把 .env 文本中秘密字段的值替换为 VAULT: 占位引用（非秘密原样保留）。

    change_me 占位值与 read_env_secrets 一致跳过：它们不是秘密、不会导入秘密库，
    糊化它们会留下永远无法解析的悬空 VAULT: 引用。"""
    fmap = secret_field_map(components)
    out = []
    for line in text.splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#") and "=" in clean:
            key, _, value = clean.partition("=")
            key = key.strip()
            if (key in fmap and value.strip()
                    and not value.strip().startswith(VAULT_PREFIX)
                    and "change_me" not in value.lower()):
                indent = line[:len(line) - len(line.lstrip())]
                out.append(f"{indent}{key}={mask_ref(fmap[key]['scope'], key)}")
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def resolve_ref(ref: str) -> str:
    """把 VAULT:<scope>/<name> 解析为真实值；缺条目抛错，锁定经 store 抛 VaultLocked。"""
    scope, _, name = ref.partition("/")
    row = store.find(scope, name)
    if not row:
        raise ValueError(f"秘密库缺少条目：{ref}")
    return store.decrypt_value(row).decode("utf-8")


def resolve_env_text(text: str) -> str:
    """渲染：把文本中的 VAULT: 占位替换为 vault 中的真实值。"""
    out = []
    for line in text.splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#") and "=" in clean:
            key, _, value = clean.partition("=")
            value = value.strip()
            if value.startswith(VAULT_PREFIX):
                indent = line[:len(line) - len(line.lstrip())]
                out.append(f"{indent}{key.strip()}={resolve_ref(value[len(VAULT_PREFIX):])}")
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def migrate_env_to_masked(components: dict, actor: str = "supervisor") -> int:
    """启动迁移：.env 中仍是明文的秘密先导入 vault（以 .env 现实为准），再糊化该文件。
    库锁定时拒绝迁移（绝不把值抹成占位后解不开）。返回迁移条数。"""
    path = PROFILE.install_root / ".env"
    if not path.is_file():
        return 0
    if not read_env_secrets(components):
        return 0  # 没有明文秘密（已是糊化态或无秘密），不动
    if store.lock_state()["locked"]:
        print("[WARN] 秘密库已锁定，跳过 .env 糊化迁移（请先解锁）")
        return 0
    result = import_env(components, actor=actor, force=True)
    masked = mask_env_text(path.read_text(encoding="utf-8"), components)
    tmp = path.with_suffix(".mask.tmp")
    tmp.write_text(masked, encoding="utf-8", newline="\n")
    import os
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    audit(actor, "vault.env_masked", "", f"migrated={result['imported']}")
    print(f"[INFO] .env 已糊化：{result['imported']} 个秘密字段改为 VAULT: 引用（ADR-0045）")
    return result["imported"]


def apply_chronicler_secrets() -> int:
    """启动时（db 就绪后）把糊化的 Chronicler 自身秘密从秘密库解析进进程。

    config._load_dotenv 在 import 时跳过 VAULT: 引用；本函数在 normal 模式启动时
    （迁移之后、服务之前）解析 CHRONICLER_SECRET / CHRONICLER_OIDC_SECRET 等自身秘密，
    更新 os.environ + Cfg，并重建 import 时固化的签名器。返回解析条数。
    """
    path = PROFILE.install_root / ".env"
    if not path.is_file():
        return 0
    resolved = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, _, value = clean.partition("=")
        key, value = key.strip(), value.strip()
        if key in GLOBAL_SECRETS and value.startswith(VAULT_PREFIX):
            resolved[key] = resolve_ref(value[len(VAULT_PREFIX):])  # 锁定/缺条目会抛错
    if not resolved:
        return 0
    import os
    for key, value in resolved.items():
        os.environ[key] = value
    from ..config import Cfg
    if "CHRONICLER_SECRET" in resolved:
        Cfg.SESSION_SECRET = resolved["CHRONICLER_SECRET"]
        from .. import auth
        auth.refresh_signer()
        from ..routers import oidc
        oidc.refresh_serializer()
    if "CHRONICLER_OIDC_SECRET" in resolved:
        Cfg.OIDC_CLIENT_SECRET = resolved["CHRONICLER_OIDC_SECRET"]
    return len(resolved)

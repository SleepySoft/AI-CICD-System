"""age 主密钥管理（ADR-0041/0044，docs/how/secrets-vault.md §4）。

主密钥存于 <install_root>/secrets/master.key（chmod 600，永不入库、永不落 data/）。
可用环境变量 CHRONICLER_SECRETS_DIR 覆盖 secrets 目录（测试用）。
密文为标准 age 格式，可用 `age -d -i master.key` 离线解密，不依赖 Chronicler。

关键约束：load/generate/write 分离——是否允许生成新密钥由 vault.store 依据
"库中是否已有秘密"裁决（锁定语义），本模块只做纯文件与加解密操作。
"""
import os
from pathlib import Path

import pyrage
from pyrage import x25519

from ..runtime import PROFILE

_KEY_PREFIX = "AGE-SECRET-KEY-"


def secrets_dir() -> Path:
    override = os.environ.get("CHRONICLER_SECRETS_DIR", "").strip()
    path = Path(override) if override else PROFILE.install_root / "secrets"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass  # Windows 无 POSIX 权限位
    return path


def master_key_path() -> Path:
    return secrets_dir() / "master.key"


def parse_identity(text: str) -> "x25519.Identity":
    """从密钥文件文本中提取 AGE-SECRET-KEY 行（容忍注释行）。"""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(_KEY_PREFIX):
            return x25519.Identity.from_str(line)
    raise ValueError("密钥文件中找不到 AGE-SECRET-KEY 行")


def load_identity() -> "x25519.Identity | None":
    """读取现有主密钥；文件不存在返回 None（绝不生成）。"""
    path = master_key_path()
    if not path.exists():
        return None
    return parse_identity(path.read_text(encoding="utf-8"))


def write_identity(identity: "x25519.Identity"):
    """把身份写入 master.key（首次生成或解锁收养）；原子替换 + chmod 600。"""
    path = master_key_path()
    content = ("# Chronicler 秘密库主密钥（ADR-0041）\n"
               "# 请立即转存密码管理器并离线备份；丢失且无副本时全部秘密不可恢复。\n"
               f"# public key: {identity.to_public()}\n"
               f"{identity}\n")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def generate_identity() -> "x25519.Identity":
    """生成新主密钥并落盘。调用方必须确保库中无既有秘密（见 store._identity_verified）。"""
    identity = x25519.Identity.generate()
    write_identity(identity)
    return identity


def recipient_str(identity: "x25519.Identity | None" = None) -> str:
    identity = identity or load_identity()
    return str(identity.to_public()) if identity else ""


def encrypt(data: bytes, identity: "x25519.Identity") -> bytes:
    return pyrage.encrypt(data, [identity.to_public()])


def decrypt(blob: bytes, identity: "x25519.Identity") -> bytes:
    return pyrage.decrypt(blob, [identity])

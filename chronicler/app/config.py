"""全局配置：进程环境变量优先，缺省回落仓库根 .env（ADR-0020：supervisor 运行于 docker 宿主侧）

IDE 调试/直接运行时无需手动 source .env——本模块导入时自动加载（不覆盖已有环境变量）。
"""
import os
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent  # chronicler/


def _load_dotenv():
    env_file = PKG_ROOT.parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())  # 已有环境变量优先


_load_dotenv()


class Cfg:
    # 站点与监听
    HOST = os.environ.get("CHRONICLER_HOST", "0.0.0.0")
    PORT = int(os.environ.get("CHRONICLER_PORT", "8600"))

    # 数据根（NFR-008 + ADR-0026 二分 + 工作空间层）：
    # private 存 db/runs；public 存 reports；workspace 存工程克隆（可由 git 重建，不进备份）
    DATA = Path(os.environ.get("CHRONICLER_DATA", PKG_ROOT.parent / "data" / "private" / "chronicler"))
    PUBLIC = Path(os.environ.get("CHRONICLER_PUBLIC", PKG_ROOT.parent / "data" / "public"))
    WORKSPACE = Path(os.environ.get("CHRONICLER_WORKSPACE", PKG_ROOT.parent / "data" / "workspace"))

    # 会话
    SESSION_SECRET = os.environ.get("CHRONICLER_SECRET", "chronicler-secret-change-me")
    SESSION_COOKIE = "chronicler_session"
    SESSION_MAX_AGE = 8 * 3600

    # 站点对外地址（OIDC 回调等）
    PUBLIC_URL = os.environ.get("CHRONICLER_PUBLIC_URL", "http://app.localhost")

    # 鉴权后端（FR-MGR-017）：local（本地账密，默认）| oidc（Keycloak）
    AUTH_BACKEND = os.environ.get("CHRONICLER_AUTH_BACKEND", "local")
    KC_PUBLIC = os.environ.get("KC_PUBLIC_URL", "http://sso.localhost")  # 浏览器可达
    KC_INTERNAL = os.environ.get("KC_INTERNAL_URL", "http://127.0.0.1")  # 宿主回源（经 Caddy）
    KC_HOST_HEADER = os.environ.get("KC_HOST_HEADER", "sso.localhost")
    KC_REALM = os.environ.get("KC_REALM", "aisystem")
    OIDC_CLIENT_ID = os.environ.get("CHRONICLER_OIDC_CLIENT_ID", "chronicler")
    OIDC_CLIENT_SECRET = os.environ.get("CHRONICLER_OIDC_SECRET", "")

    # 注册表（热更新：随包携带的只读配置，用户可在 DATA 下覆盖）
    CONFIG_DIR = Path(os.environ.get("CHRONICLER_CONFIG", PKG_ROOT / "config"))
    PROMPTS_DIR = Path(os.environ.get("CHRONICLER_PROMPTS", PKG_ROOT / "prompts"))

    @classmethod
    def db_path(cls) -> Path:
        return cls.DATA / "chronicler.db"

    @classmethod
    def repos_dir(cls) -> Path:
        return cls.WORKSPACE / "repos"

    @classmethod
    def runs_dir(cls) -> Path:
        return cls.DATA / "runs"

    @classmethod
    def reports_dir(cls) -> Path:
        return cls.PUBLIC / "reports"

    @classmethod
    def prompts_override_dir(cls) -> Path:
        return cls.DATA / "prompts"

    @classmethod
    def ensure_dirs(cls):
        for d in (cls.DATA, cls.repos_dir(), cls.runs_dir(), cls.reports_dir(), cls.prompts_override_dir()):
            d.mkdir(parents=True, exist_ok=True)

"""全局配置：全部来自环境变量（见 .env.example）"""
import os


class Cfg:
    # 站点
    PUBLIC_URL = os.environ.get("MANAGER_PUBLIC_URL", "http://app.localhost")

    # Keycloak OIDC
    KC_PUBLIC = os.environ.get("KC_PUBLIC_URL", "http://sso.localhost")      # 浏览器可达
    KC_INTERNAL = os.environ.get("KC_INTERNAL_URL", "http://keycloak:8080")  # 容器间回源
    KC_REALM = os.environ.get("KC_REALM", "aisystem")
    OIDC_CLIENT_ID = os.environ.get("OIDC_MANAGER_CLIENT_ID", "manager")
    OIDC_CLIENT_SECRET = os.environ.get("OIDC_MANAGER_SECRET", "manager-oidc-secret-change-me")

    # 会话
    SESSION_SECRET = os.environ.get("MANAGER_SESSION_SECRET", "manager-session-secret-change-me")
    SESSION_COOKIE = "aisystem_session"
    SESSION_MAX_AGE = 8 * 3600

    # ATR（terminal-runtime）
    ATR_BASE = os.environ.get("ATR_BASE_URL", "http://terminal-runtime:18650")
    ATR_TOKEN = os.environ.get("ATR_API_TOKEN", "")

    # 工具注册表
    TOOLS_YAML = os.environ.get("TOOLS_YAML", "tools.yaml")

    # Agent 注册表（M1.5 过渡形态，M2 迁移 Postgres，见 docs/what/manager.md §2.1）
    AGENTS_YAML = os.environ.get("AGENTS_YAML", "agents.yaml")
    AGENTS_ROOT = os.environ.get("AGENTS_ROOT", "/opt/agents")  # 只读挂载，探测安装状态

    # 角色
    BOSS_GROUP = "boss"
    DEV_GROUP = "dev"

    @classmethod
    def realm_url(cls, public: bool = True) -> str:
        base = cls.KC_PUBLIC if public else cls.KC_INTERNAL
        return f"{base}/realms/{cls.KC_REALM}"

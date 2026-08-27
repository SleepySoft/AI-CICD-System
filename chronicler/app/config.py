"""全局配置：全部来自环境变量（ADR-0020：supervisor 运行于 docker 宿主侧）"""
import os
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent  # chronicler/


class Cfg:
    # 站点与监听
    HOST = os.environ.get("CHRONICLER_HOST", "0.0.0.0")
    PORT = int(os.environ.get("CHRONICLER_PORT", "8600"))

    # 数据根（NFR-008 显式落宿主；默认 <repo>/data/chronicler）
    DATA = Path(os.environ.get("CHRONICLER_DATA", PKG_ROOT.parent / "data" / "chronicler"))

    # 会话
    SESSION_SECRET = os.environ.get("CHRONICLER_SECRET", "chronicler-secret-change-me")
    SESSION_COOKIE = "chronicler_session"
    SESSION_MAX_AGE = 8 * 3600

    # 注册表（热更新：随包携带的只读配置，用户可在 DATA 下覆盖）
    CONFIG_DIR = Path(os.environ.get("CHRONICLER_CONFIG", PKG_ROOT / "config"))
    PROMPTS_DIR = Path(os.environ.get("CHRONICLER_PROMPTS", PKG_ROOT / "prompts"))

    @classmethod
    def db_path(cls) -> Path:
        return cls.DATA / "chronicler.db"

    @classmethod
    def repos_dir(cls) -> Path:
        return cls.DATA / "repos"

    @classmethod
    def runs_dir(cls) -> Path:
        return cls.DATA / "runs"

    @classmethod
    def reports_dir(cls) -> Path:
        return cls.DATA / "reports"

    @classmethod
    def prompts_override_dir(cls) -> Path:
        return cls.DATA / "prompts"

    @classmethod
    def ensure_dirs(cls):
        for d in (cls.DATA, cls.repos_dir(), cls.runs_dir(), cls.reports_dir(), cls.prompts_override_dir()):
            d.mkdir(parents=True, exist_ok=True)

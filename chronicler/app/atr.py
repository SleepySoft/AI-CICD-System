"""ATR（terminal-runtime）客户端：工程常驻会话（ADR-0046）。

supervisor 侧唯一的 ATR 集成点：回源走 Caddy（127.0.0.1 + Host 头，同 OIDC 回源惯例）；
API token 从环境变量/糊化 .env 引用的秘密库解析。会话命名 atr-proj-<工程id>，
tmux 后端跨重启存活（ATR 自动收养）。
"""
import os
from pathlib import Path

import httpx

from .config import Cfg
from .runtime import PROFILE

_COMPONENT = "terminal-runtime"  # ATR 组件名（本模块是唯一集成点）


def _public_base() -> str:
    """ATR 对外地址（组件 plugin.yaml 自述 url，去掉页面路径）。"""
    from .tools import get_tool
    url = (get_tool(_COMPONENT).get("url") or "http://term.localhost/ui").rstrip("/")
    return url.removesuffix("/ui").removesuffix("/chat")


def _token() -> str:
    tok = os.environ.get("ATR_API_TOKEN", "").strip()
    if tok and not tok.startswith("VAULT:"):
        return tok
    try:
        from .vault import sync
        return sync.resolve_ref("terminal-runtime/ATR_API_TOKEN")
    except Exception:  # noqa: BLE001
        return ""


def _client() -> httpx.Client:
    # 宿主回源：容器不发布端口，经 Caddy 80 按 Host 头分流（term.localhost）
    headers = {"Host": "term.localhost"}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"  # 空 token = ATR 未开鉴权，不带空头
    return httpx.Client(base_url="http://127.0.0.1", timeout=15, trust_env=False,
                        headers=headers)


def ensure_session(session_id: str, cwd: str = "", purpose: str = "") -> bool:
    """幂等创建会话（tmux 后端）。返回 True=新建，False=已存在。"""
    with _client() as client:
        resp = client.post("/sessions", json={
            "id": session_id, "command": "bash", "cwd": cwd or None,
            "backend": "tmux", "purpose": purpose, "ensure": True,
            "tags": ["chronicler", "project-session"]})
        if resp.status_code == 409:  # 未开 ensure 的存量兼容
            return False
        resp.raise_for_status()
        body = resp.json()
        return bool(body.get("created", True))


def send_text(session_id: str, text: str):
    """向会话发送文本并回车（bracketed paste，多行安全）。"""
    with _client() as client:
        for action in ({"type": "paste", "text": text}, {"type": "key", "key": "enter"}):
            resp = client.post(f"/sessions/{session_id}/actions",
                               json={"actor": "chronicler", "action": action})
            resp.raise_for_status()


def session_exists(session_id: str) -> bool:
    with _client() as client:
        resp = client.get("/sessions")
        if resp.status_code != 200:
            return False
        items = resp.json()
    items = items if isinstance(items, list) else items.get("sessions", [])
    return any((s.get("id") or s.get("session_id")) == session_id for s in items)


def chat_url(session_id: str) -> str:
    """直达指定会话的对话页链接（token 随链接，首次点击后页面自行持久化）。"""
    return f"{_public_base()}/chat?session={session_id}&token={_token()}"


def container_repo_path(pid: int) -> str:
    """工程克隆在 ATR 容器内的路径（compose 挂载 DATA_ROOT/workspace → /workspace）。"""
    return f"/workspace/repos/{pid}"


def write_context_file(project: dict, skills: list[str]) -> Path | None:
    """把工程上下文写入克隆根（ATR_CONTEXT.md；ATR 容器内经 /workspace 可见）。"""
    from .config import Cfg
    dest = Cfg.repos_dir() / str(project["id"])
    if not dest.is_dir():
        return None
    lines = [
        f"# 工程上下文：{project['name']}", "",
        f"- Git：{project.get('git_url', '')}",
        f"- 默认分支：{project.get('default_branch') or '远端默认'}",
        f"- 容器内工作目录：/workspace/repos/{project['id']}", "",
        "## 工作纪律", "",
        "- 只在本目录内做 git 写操作；禁止对宿主仓库执行 reset/checkout 等操作。",
        "- 秘密不在环境中；需要凭据请找管理员从秘密库获取。", "",
    ]
    if skills:
        lines += ["## 可用组件能力", ""] + [f"- {s}" for s in skills] + [""]
    path = dest / "ATR_CONTEXT.md"
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path

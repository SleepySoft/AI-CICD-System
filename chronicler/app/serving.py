"""supervisor 启动时的 HTTP 监听（双栈）。

背景（2026-09-03 实测）：``uvicorn.run(host="0.0.0.0")`` 只绑 IPv4，部分客户端把
``localhost`` 解析成 ``::1`` 且不做回落时会连不上；而 ``uvicorn.run(host="::")``
在 Windows 上又默认纯 IPv6（``127.0.0.1`` 连不上）。因此默认（host=0.0.0.0）
改为显式双监听：IPv4 ``0.0.0.0`` + IPv6 ``[::]``（V6ONLY），保证本机
``localhost/127.0.0.1/[::1]`` 与容器回源（IPv4 全网卡）都可达。
显式设置 ``CHRONICLER_HOST`` 时保持单监听语义（如 ``127.0.0.1`` 只留回环）。
"""

from __future__ import annotations

import socket
import sys

import uvicorn
from uvicorn import Config, Server


def _bind(addr: str, port: int, backlog: int, v6only: bool = False) -> socket.socket:
    family = socket.AF_INET6 if ":" in addr else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if family == socket.AF_INET6 and v6only:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    sock.bind((addr, port))
    sock.listen(backlog)
    sock.set_inheritable(True)
    return sock


def _print_banner(port: int, ipv6_ok: bool) -> None:
    print("[OK] Chronicler supervisor 已启动，访问入口：")
    print(f"      本机浏览器  ->  http://127.0.0.1:{port}/")
    if ipv6_ok:
        print(f"      localhost   ->  http://localhost:{port}/   （IPv4/IPv6 双栈均监听）")
    else:
        print(f"      localhost   ->  http://localhost:{port}/   （仅 IPv4）")
    print("      底座/工具 API（经 Caddy 反代）->  http://app.localhost 或 http://localhost")


def serve(app, host: str, port: int) -> None:
    """按 host/port 启动 uvicorn。

    host 为 0.0.0.0（默认）时同时监听 IPv6 通配 [::]，保证
    localhost/127.0.0.1/[::1] 与容器回源（IPv4 全网卡）都可达。
    其余 host 语义与 ``uvicorn.run(host=...)`` 一致。
    """
    if host != "0.0.0.0":
        uvicorn.run(app, host=host, port=port)
        return

    config = Config(app, host=host, port=port, log_level="info")
    sockets: list[socket.socket] = []
    ipv6_ok = False
    try:
        sockets.append(_bind("0.0.0.0", port, config.backlog))
    except OSError as exc:
        for sock in sockets:
            sock.close()
        sys.exit(f"[ERROR] 无法监听 0.0.0.0:{port}：{exc}")
    try:
        sockets.append(_bind("::", port, config.backlog, v6only=True))
        ipv6_ok = True
    except OSError as exc:
        print(f"[WARN] IPv6 不可用，跳过 [::]:{port}：{exc}", file=sys.stderr)

    _print_banner(port, ipv6_ok)
    Server(config).run(sockets=sockets)

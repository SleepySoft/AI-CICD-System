#!/usr/bin/env python3
"""DOM 级页面巡检（经 Kimi WebBridge 驱动真实浏览器，含登录态）
前置：webbridge 守护进程运行 + 浏览器扩展已连接（~/.kimi-webbridge/bin/kimi-webbridge status）
用法: python scripts/verify-pages-dom.py
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:10086/command"
SESSION = "chronicler-dom-check"


def call(action, args=None):
    body = json.dumps({"action": action, "args": args or {}, "session": SESSION}).encode()
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    if not d.get("ok"):
        raise RuntimeError(f"{action} 失败: {d}")
    return d.get("data", {})


def evaljs(code):
    return call("evaluate", {"code": code}).get("value")


def main():
    call("navigate", {"url": "http://app.localhost", "newTab": True,
                      "group_title": "Chronicler DOM 巡检"})
    time.sleep(3)

    logged_in = evaljs("(function(){return !!document.querySelector('.el-tabs')})()")
    if not logged_in:
        print("[FAIL] 未登录（请先在浏览器登录 Chronicler 后重跑）")
        return 1

    ok = True
    for tab, check in (
        ("工程", "document.querySelectorAll('[id^=\"pane-projects\"] .el-table__body tr').length"),
        ("任务", "document.querySelectorAll('[id^=\"pane-runs\"] .el-table__body tr').length"),
        ("配置", "document.querySelectorAll('[id^=\"pane-config\"] .card-box').length"),
    ):
        evaljs(f"(function(){{var tabs=[...document.querySelectorAll('.el-tabs__item')];"
               f"var t=tabs.find(x=>x.innerText.trim()==='{tab}'); if(t) t.click(); return !!t}})()")
        time.sleep(1.5)
        n = evaljs(check)
        status = "OK " if n and int(n) > 0 else "!!!"
        print(f"{status} {tab} 页表格/卡片行数 = {n}")
        if not n or int(n) == 0:
            ok = False

    # 冒烟断言：工程表格首行单元格数（抓"自闭合标签吞列"这类回归）
    cells = evaljs("(function(){var r=document.querySelector('[id^=\"pane-projects\"] "
                   ".el-table__body tr'); return r ? r.querySelectorAll('td').length : 0})()")
    status = "OK " if cells and int(cells) >= 5 else "!!!"
    print(f"{status} 工程表首行单元格数 = {cells}（应≥5）")
    if not cells or int(cells) < 5:
        ok = False

    call("close_session")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

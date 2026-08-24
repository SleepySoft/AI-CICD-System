#!/bin/bash
# 在虚拟桌面上打开一个"有头"浏览器（在 noVNC 页面中可见）
# 用法: docker exec aisystem-browsers-1 open-browser [chromium|firefox|webkit] [URL]
BROWSER="${1:-chromium}"
URL="${2:-about:blank}"
export DISPLAY=:0
exec npx playwright open --browser "${BROWSER}" "${URL}"

#!/bin/sh
# Outline 内网 HTTP 部署补丁：production 会把 OAuth cookie 标 secure（HTTP 下登录 500）
# 启动前把 secure 标记关掉；镜像升级后若文件结构变化需复评本补丁
set -e
sed -i 's/secure: _env.default.isProduction/secure: false/g' /opt/outline/build/server/utils/passport.js
exec node build/server/index.js

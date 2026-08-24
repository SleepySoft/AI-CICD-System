# 生产部署指南

目标：**服务挂了会话不丢，机器重启服务自启，agent 随时能找回会话。**

架构要点：

```text
systemd ──守护──> ATR service (FastAPI)
                     │ attach/detach（可随时重启）
                     ▼
                  tmux server ──持有──> 真实目标程序（kimi / vim / bash ...）
```

- **tmux 后端**：目标程序跑在独立的 tmux server 里。ATR service 只是 attach 进去的观察者，它崩溃/重启/升级都不会影响会话。
- **自动找回**：service 启动时自动 adopt 所有带 `atr-` 前缀的 tmux 会话，agent 调 `GET /sessions` 就能看到原来的 session id。
- **systemd 守护**：service 崩溃 2 秒内自动拉起。

## 部署步骤（Linux / systemd）

```bash
# 1. 安装依赖（tmux >= 3.2 以支持 -e 环境变量传递）
sudo apt install tmux python3-venv

# 2. 创建专用用户并放置代码
sudo useradd -r -m -s /bin/bash atr
sudo mkdir -p /opt && sudo cp -r . /opt/terminal-runtime-skill
sudo chown -R atr:atr /opt/terminal-runtime-skill

# 3. 创建虚拟环境
sudo -u atr python3 -m venv /opt/terminal-runtime-skill/.venv
sudo -u atr /opt/terminal-runtime-skill/.venv/bin/pip install -r /opt/terminal-runtime-skill/requirements.txt

# 4. 安装并启动服务
sudo cp deploy/terminal-runtime.service /etc/systemd/system/
#   如需远程访问，先编辑 unit：ATR_HOST=0.0.0.0 + ATR_API_TOKEN=<随机长token>
sudo systemctl daemon-reload
sudo systemctl enable --now terminal-runtime

# 5. 验证
curl http://127.0.0.1:18650/health
```

## 安全红线

- **不要把无 token 的服务绑到非 loopback 地址。** 服务已内置闸门：这种配置会拒绝启动（除非显式 `ATR_ALLOW_INSECURE_LISTEN=1`）。
- 远程访问时 agent 侧配置：`ATR_BASE_URL=http://<host>:18650`、`ATR_API_TOKEN=<token>`，client 会自动携带。
- 更稳妥的做法是不开放端口，走 SSH 端口转发：`ssh -L 18650:127.0.0.1:18650 user@host`。

## 日常运维

```bash
# 服务日志
journalctl -u terminal-runtime -f

# 人类想直接看某个会话的屏幕（与 service 共用 atr 用户）
sudo -u atr tmux attach -t atr-<session-id>

# 强制 service 重新发现会话（正常不需要，启动时会自动 adopt）
curl -X POST http://127.0.0.1:18650/sessions/reattach
```

## 升级流程（验证"会话不丢"）

```bash
sudo -u atr git -C /opt/terminal-runtime-skill pull
sudo -u atr /opt/terminal-runtime-skill/.venv/bin/pip install -r /opt/terminal-runtime-skill/requirements.txt
sudo systemctl restart terminal-runtime   # tmux 后端会话在此刻依然存活
curl http://127.0.0.1:18650/sessions      # 原会话已被自动找回
```

注意：**pty 后端的会话随 service 生死**，只有 tmux 后端具备持久性。生产环境请保持 `ATR_DEFAULT_BACKEND=tmux`。

# Runbook: 接入一家新 Agent（注册 / 安装 / 首次登录）

> 版本：v1.0 · 日期：2026-08-26 · 状态：生效
> 适用：核心栈已启动（terminal-runtime + manager 健康），操作者为 boss 角色
> 关联：manager/agents.yaml、scripts/agents/、FR-MGR-002、ADR-0017、ADR-0018

## 目的

让 Manager 知道一家 agent 的存在，并把它的 CLI 安装到持久卷、完成首次登录，之后可在 Agent 终端一键拉起长会话。

## 步骤

1. **注册**：在 `manager/agents.yaml` 的 `agents:` 下加一条记录（字段含义见文件头注释）——
   `name / cli_type / command / install / env / api_key_ref / extra_args / max_runtime_sec`。
   `api_key_ref` 只写环境变量名（如 `LLM_API_KEY`），密钥值写在 `.env`，**绝不写进 YAML**。
2. **写安装脚本**：新增 `scripts/agents/<name>.sh`（LF 行尾），要求幂等、锁版本、
   装完写 `/opt/agents/<name>/VERSION`；参照 `aider.sh` / `kimi.sh`。
3. **重装挂载生效**：YAML 与脚本均为只读挂载，改内容即热更新；首次新增挂载点后需
   `docker compose up -d terminal-runtime manager`。
4. **安装**：Manager 页面 → Agent 终端 → 注册表区域点该 agent 的「安装」，
   在会话 `install-<name>` 中观察进度，看到 `[install] 完成` 即成功。
5. **首次登录**（OAuth/网页类）：以该 agent 创建会话（下拉选择，勿选手填命令），
   在终端里人工完成一次登录；凭据随 `/opt/agents/<name>/`（HOME 指向此处）持久化，
   后续无需重复。API key 类在 `.env` 填好 `LLM_API_KEY` 即可，无需此步。
6. **拉起使用**：Agent 下拉选择该 agent，填会话 ID 创建；此后 Manager 以
   observe → act → wait 原语驱动（见 `third_party/terminal-runtime-skill/SKILL.md`）。

## 验证

```bash
bash scripts/verify-manager.sh   # 含 /api/agents 401 检查与持久卷挂载探测
```

预期输出：`app /api/agents -> 401`（未登录受保护）与 `AGENTS-VOLUME-OK`；
登录后 `GET /api/agents` 返回注册表且该 agent `installed: true`。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| 创建会话后命令不存在 | 未执行安装或 VERSION 缺失 | 先点「安装」；检查 `data/agents/<name>/VERSION` |
| 安装会话报 pip 超时 | 镜像源不可达 | 确认脚本用清华源；容器网络/代理排查 |
| OAuth 登录态丢失 | 会话 env 未带 HOME=/opt/agents/<name> | 必须经 Agent 下拉创建（勿手填命令），保证注册表注入 env |
| 修改 YAML 后接口未变 | 文件语法错误 | `docker compose exec manager python -c "import yaml;yaml.safe_load(open('agents.yaml'))"` |

## 回滚（如适用）

删除 `manager/agents.yaml` 中对应记录即可下架；`data/agents/<name>/` 目录可保留（含登录态）或整体删除以彻底清理。

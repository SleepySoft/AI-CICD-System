# ADR-0047 OIDC 客户端注册收归 Keycloak 组件 oidc 能力

> 日期：2026-09-07 · 状态：已接受
> 关联：[ADR-0025 能力存在即声明](0025-skill-existence-as-declaration.md)、[ADR-0027 组件目录与钩子](0027-component-directory-hooks.md)、
> [ADR-0037 单一入口 Web 初始化](0037-single-entry-web-init.md)；docs/how/sso-wiring.md

## 背景

- Chronicler 自身的 SSO 登录是 OIDC 客户端，此前由老脚本 `scripts/wire-chronicler.sh`
  手工注册进 Keycloak（含 profile/email scope 补建）。该脚本按 ADR-0037/0038 属于待回收
  的初始化期脚手架，且在秘密库糊化（ADR-0045）后已不可直接运行——`source .env` 拿到的
  是 `VAULT:` 占位引用。
- 2026-09-07 重建环境底座时确认：realm 模板不含任何客户端（`clients: []`），gitea/outline
  等组件由各自 initialize hook 幂等注册客户端（消费方自负），而 Chronicler 是核心、不是
  组件，没有承载这一逻辑的组件 hook，重建后 SSO 断链只能人工介入。
- 核心禁止出现组件名/接线知识（ADR-0027），因此不能由核心硬编码 Keycloak 客户端注册逻辑。

## 决策

Keycloak 组件新增通用能力脚本 `hooks/oidc.py`（`upsert-client <client_id> <secret>
<base_url> <callback_path>`）：幂等创建/更新 OIDC 客户端（密钥、回调地址、登出地址），
并补建 realm 模板缺失的 profile/email scope 及其 claim 映射。Chronicler 自身客户端的
接线当前由管理员显式触发一次该能力完成；核心到组件的反向特定调用（自动联动）暂缓，
留待"核心消费组件能力"的通用机制设计。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 核心硬编码 Keycloak 客户端注册 | 违反 ADR-0027「核心不含组件知识」 |
| 继续保留 wire-chronicler.sh 手工路径 | 糊化 .env 后脚本取到 VAULT: 占位即失败；且属待回收脚手架（ADR-0037/0038） |
| 初始化流程自动调用该能力（核心→组件反向依赖） | 需要通用机制支撑，当前需求仅此一例；暂缓避免过度设计 |
| 把 chronicler 客户端塞进 realm 模板 | 模板是静态 JSON，密钥不能入库（ADR-0045），客户端 secret 必须运行时注入 |

## 后果

- 正面：OIDC 客户端注册有了组件自有的幂等能力，任何消费方（含未来的核心）都可经
  `run_capability("oidc.py", ...)` 调用；栈重建后人工接线从"跑 bash 脚本"降为
  "调一次能力"，且秘密经秘密库解析、不经 .env 明文。
- 负面：Chronicler SSO 在栈重建后仍需一次手动触发，直到核心侧联动机制落地；
  能力脚本依赖 Keycloak 容器健康，调用时序由调用方保证。
- 同步更新：AGENTS.md 能力清单；docs/how/sso-wiring.md §2.2（运行时接线的现状描述）。

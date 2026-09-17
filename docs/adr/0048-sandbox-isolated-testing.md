# ADR-0048 组件测试沙箱：环境级五通道隔离与现拉现建现测现毁

> 日期：2026-09-16 · 状态：已接受
> 关联：[how/sandbox-testing.md](../how/sandbox-testing.md)、[runbooks/testing.md](../runbooks/testing.md)；FR-ENV-003、FR-MGR-023

## 背景

组件可达性/可登录性测试需要在 CI 里"现拉、现部署、现测、现毁"地起完整组件栈，且**与运行中的生产栈同处一个 dockerd**（自举：Jenkins 自身就是被测组件之一）。早期 `deploy_test` 只做了项目名与临时数据目录两项隔离，实测仍会冲突：

- 组件 compose 统一声明加入 external 共享网络 `aisystem`——测试容器以 `gitea`/`postgres` 等相同 DNS 别名注册进**生产网络**，Caddy 可能把生产流量轮询进测试容器，测试 gitea 会连上生产 postgres；
- 宿主端口（80/22222/…）直接碰撞；
- 复用生产 `.env` 的真实凭据 → 测试栈可登录生产服务写数据；
- Chronicler/Jenkins 父进程环境里残留的生产 `.env` 值，经 compose"进程环境 > --env-file"优先级**静默覆盖**沙箱 env（实测：沙箱 caddy 抢绑生产 80 端口）。

核心认知：**Docker 隔离的是进程，不是环境**。同 dockerd 上两套栈只要共享网络名/端口/凭据/数据路径中任意一项，逻辑上就不是两个系统。

## 决策

1. **能探测就不复制**：生产可达性巡检（verify-auth.py 等）只读探测运行中的栈，零环境复制；"代码对不对"的验证才进沙箱。
2. 沙箱 = **环境级五通道隔离**（不是靠任何新技术，而是系统性切断全部共享通道）：
   独立 compose 项目名；程序化改写 compose（external 网络→项目内建、剥离宿主端口仅留沙箱入口、
   去 restart 策略防销毁期复活、剔除逃逸生产的 `*.localhost` extra_hosts）；临时 DATA_ROOT；
   按 setup.yaml 字段声明现场生成一次性秘密（不读生产 .env/秘密库）；子进程环境按 compose
   引用变量全量清洗。
3. 生命周期**现拉现建现测现毁**：按 setup.yaml `depends_on` 拓扑分波起栈、readiness 等待、
   Host 头探针（含认证探针真登录）、`down -v` + 按项目标签强制兜底清理，零残留。
4. 秘密轮换传播保持**被动人工收敛**（vault 单点写入，重新部署才生效），但配"待传播横幅"
   让未收敛状态在全部界面可见——被动不等于隐身。
5. 组件特有坑由组件自述（plugin.yaml `sandbox.env`/`probe.expect`/`auth`），核心零硬编码。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 只靠 Docker 默认隔离（容器/文件系统） | 不解决网络别名冲突、端口争抢、凭据共享——实测三重踩坑 |
| 另起独立 dockerd/VM 跑测试 | 资源与运维成本高，CI 自举场景不可行（Jenkins 在该 dockerd 里） |
| 测试打生产栈（只读探测）充当全部验证 | 巡检能答"活着的系统通不通"，答不了"代码改动对不对"；二者互补不可互替 |
| 轮换即自动全量重建容器 | 生产组件被动重启风险大；收敛时机应由人控制（辅以横幅可见性） |
| 在核心硬编码各组件的测试期望 | 违反 ADR-0027"组件归组件"；新增组件需改核心代码 |

## 后果

- 正面：CI 每次提交可全量验证 12 个组件的可达+可登录；生产零干扰（实测三轮构建期间 13 个
  生产容器零重启）；新增组件自动纳入测试。
- 负面：全量一轮数分钟（镜像本地缓存后 ~5 分钟）；沙箱内不跑 initialize 钩子，sso/needs_hook
  类认证在沙箱跳过，由生产巡检覆盖。
- 同步更新：docs/how/sandbox-testing.md（机制）、docs/runbooks/testing.md（操作）、
  AGENTS.md（命令与坑清单）、requirements/traceability.md（FR-ENV-003 验证方式）。

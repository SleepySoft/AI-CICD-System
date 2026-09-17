# 沙箱测试机制（how）——组件可达性/可登录性的环境级隔离验证

> 版本：v1.0 · 日期：2026-09-16 · 状态：生效
> 定位：沙箱测试（`python -m chronicler sandbox`）的内部实现机制与设计原理；操作步骤见
> [runbooks/testing.md](../runbooks/testing.md)；决策背景见 [ADR-0048](../adr/0048-sandbox-isolated-testing.md)
> 关联需求：FR-ENV-003、FR-MGR-023

## 1. WHY 摘要

Docker 隔离进程但不隔离环境：同 dockerd 上两套栈共享网络别名、宿主端口、凭据、数据路径，
互相纠缠（ADR-0048 背景）。沙箱 = 系统性切断全部共享通道，让"测试用的自己"与"部署中的自己"
成为逻辑上互不可达的两个系统。

## 2. WHAT 摘要

- 契约：对全部启用组件断言入口可达（plugin.yaml `url`，期望码可被 `probe.expect` 覆盖）、
  对声明了 `auth` 的组件用沙箱现场生成的秘密验证可登录（basic/bearer/token-grant；
  sso 与 needs_hook 条目沙箱跳过，归生产巡检 scripts/verify-auth.py）；
- 输出：控制台报告 + 可选 JUnit XML（`--junit`）；退出码 0=全过，1=有失败，2=编排错误；
- 边界：不跑 initialize 钩子、不写生产 .env/秘密库、不触碰生产项目资源。

## 3. HOW 主体

### 3.1 总体流程

```
load_components（plugin.yaml+setup.yaml 合并）
  → 依赖闭包 + 拓扑分波（setup.yaml depends_on，caddy 强制入闭包作入口）
  → 端口预检（Hyper-V 排除区间早发现；--http-port 0 = 系统分配）
  → generate_env：按 setup.yaml 字段声明生成一次性秘密（password/token/hex，字母数字避免转义坑）
  → transform_compose：逐组件程序化改写 YAML（见 3.2）
  → Compose 子进程环境清洗（见 3.3）→ pull → 分波 up -d → readiness 等待（container-health/process）
  → 探针：Host 头经沙箱 caddy 打 127.0.0.1:<沙箱端口>，整体重试预算容忍慢启动
  → 认证探针：basic/bearer/token-grant 用沙箱秘密真登录
  → down -v + 按 com.docker.compose.project 标签强制兜底清理 → 删工作目录（--keep 除外）
```

### 3.2 compose 程序化改写（transform_compose）

| 改写 | 作用 |
|------|------|
| `networks.default: {name: aisystem, external: true}` → `{}`（项目内建） | 沙箱服务别名只在 `chronicle-sandbox_default` 内可见；生产网络看不到沙箱、沙箱也够不到生产 postgres |
| 删除非入口组件的 `ports:` | 永不抢宿主端口；探针统一经沙箱 caddy 按 Host 头进入 |
| 删除 `restart:` | 停止即终态，防止销毁阶段容器被重启策略复活（实测残留根因之一） |
| 剔除 `.localhost` 结尾的 `extra_hosts` | 防止沙箱内把组件域名解析到宿主网关逃逸到生产 caddy |
| 合并 plugin.yaml `sandbox.env` | 组件自述的沙箱专用覆盖（如 openproject 兑上游 zh-CN seed bug） |

Caddyfile 不改：沙箱 caddy 加入项目网络后，`gitea:3000` 等上游名解析到的就是沙箱容器。

### 3.3 子进程环境清洗（Compose 类）

Chronicler 的 `config._load_dotenv` 在 import 时把生产 `.env` 灌进 `os.environ`，而 compose 插值
优先级是**进程环境 > --env-file**——不清洗则生产值静默覆盖沙箱 env（实测沙箱 caddy 抢绑生产 80）。
做法：收集全部 compose 文件引用的变量名 + 底座键 + DOCKER_TLS*/DOCKER_HOST（CI agent 镜像可能
残留 TLS 配置），从子进程 env 中剔除，只由沙箱 `--env-file` 唯一供给。**任何从 chronicler 进程
拉起 compose 的代码都必须照此处理。**

### 3.4 CI 集成（docker.sock 挂载场景）

Jenkins agent 容器经 `--volumes-from` 共享 Jenkins 容器挂载 + 挂 docker.sock 操作宿主 dockerd：
- 卷挂载源必须翻译成宿主视角路径（`--host-root`，Jenkinsfile 用 service 标签动态探测
  /var/jenkins_home 的宿主来源拼出 workspace 宿主路径）；
- 探针从 agent 容器内访问 127.0.0.1 到不了宿主 → `--probe-host host.docker.internal`；
- 并发互斥用 `disableConcurrentBuilds()`（lock 插件未装）。

### 3.5 已知坑（实测记录）

- Docker Desktop Windows 上 `compose down` 常删不净（14 剩 8）→ 600s 超时 + 标签强清兜底；
- down 后宿主端口代理由延迟释放（WinError 10048 假占用），稍等自愈；
- httpx `trust_env=True` 读 Windows 系统代理（Clash 注册表），127.0.0.1 请求被劫持返 502
  且 caddy 无日志——Python HTTP 客户端一律 trust_env=False；
- compose 错误尾部截断时可能只见 `docker --help` 里的 `key.pem` 默认路径——不是 TLS 问题，
  先看完整输出（ci-agent 缺 compose 插件事故）。

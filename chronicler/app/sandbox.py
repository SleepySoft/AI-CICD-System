"""沙箱可达性测试（FR-ENV-003 自动化 / FR-MGR-023 扩展）：现拉、现部署、现测、现毁。

与生产实例的五通道隔离：
  1. 独立 compose 项目名（chronicle-sandbox）→ 容器/网络/卷名全部隔离；
  2. 程序化改写组件 compose：external 共享网络 aisystem → 项目内建网络，
     沙箱内服务别名（gitea/postgres/...）对生产网络不可见，也不会反向劫持生产解析；
  3. 剥离全部宿主端口发布（仅入口 caddy 保留，绑定沙箱专用端口），不占用生产端口；
  4. 临时 DATA_ROOT（ tempfile 或 --workdir ），绝不触碰 data/；
  5. 秘密值按各组件 setup.yaml 字段声明（generate/generate_length）现场随机生成，
     写入沙箱专用 env 文件——不读正式 .env、不碰秘密库，与部署实例无任何共享凭据。

使用：python -m chronicler sandbox [--components a,b] [--include-disabled]
           [--http-port N] [--timeout N] [--probe-timeout N] [--keep] [--junit PATH]
"""
import argparse
import json
import os
import re
import secrets
import shutil
import socket
import string
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import yaml

from .config import Cfg
from .initialization import catalog
from .runtime import PROFILE

PROJECT = "chronicle-sandbox"
ENTRY_COMPONENT = "caddy"          # 统一入口，探针经它按 Host 头路由到各组件
DEFAULT_HTTP_PORT = 18080
DEFAULT_OK_CODES = {200, 301, 302, 303, 307, 308, 401, 403}
# 必需变量：${VAR}（裸引用，空值即断线）或 ${VAR:?}（缺省直接报错）；${VAR:-default} 有兑底不算
ENV_VAR = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::\?|\})")
# 所有插值形式（含 ${VAR:-x}）：子进程环境清洗用
ENV_VAR_ALL = re.compile(r"\$\{([A-Z][A-Z0-9_]*)[}:?\-]")
# 沙箱固定提供的底座变量（即使 compose 未引用也不能从进程环境泄漏进去）
BASE_ENV_KEYS = {"TZ", "BASE_DOMAIN", "HTTP_PORT", "DATA_ROOT", "REPO_ROOT", "COMPONENTS_ROOT",
                 "SSH_KEY_PATH", "HTTP_PROXY", "HTTPS_PROXY"}


# ---------------------------------------------------------------- 组件解析

def load_components() -> dict:
    """合并 plugin.yaml（url/enabled/container/probe）与 setup.yaml（依赖/字段/就绪）"""
    setups = {name: entry["component"] for name, entry in catalog.load().items()
              if not entry.get("error")}
    result = {}
    for d in sorted(Cfg.COMPONENTS_DIR.iterdir()):
        plugin_path = d / "plugin.yaml"
        compose_path = d / "compose.yml"
        if not plugin_path.is_file() or not compose_path.is_file():
            continue
        plugin = yaml.safe_load(plugin_path.read_text(encoding="utf-8")) or {}
        name = plugin.get("name") or d.name
        result[name] = {
            "name": name, "dir": d, "compose": compose_path,
            "url": plugin.get("url") or "",
            "enabled": plugin.get("enabled", True),
            "driver": plugin.get("driver", "docker"),
            "probe": plugin.get("probe") or {},
            "sandbox_env": (plugin.get("sandbox") or {}).get("env") or {},
            "setup": setups.get(name, {"depends_on": [], "fields": [], "readiness": {}}),
        }
    return result


def resolve_closure(targets: list[str], components: dict) -> list[str]:
    """目标组件 + 依赖闭包（含入口 caddy），按 depends_on 拓扑分层返回波浪列表"""
    closure, stack = {}, list(targets) + [ENTRY_COMPONENT]
    while stack:
        name = stack.pop()
        if name in closure:
            continue
        comp = components.get(name)
        if not comp:
            raise SystemExit(f"组件未注册或缺 compose.yml：{name}（被依赖但未找到）")
        closure[name] = comp
        stack.extend(comp["setup"].get("depends_on") or [])

    waves, remaining = [], set(closure)
    while remaining:
        wave = sorted(n for n in remaining
                      if not (set(closure[n]["setup"].get("depends_on") or []) & remaining))
        if not wave:
            raise SystemExit(f"组件依赖存在环：{sorted(remaining)}")
        waves.append(wave)
        remaining -= set(wave)
    return waves


# ---------------------------------------------------------------- 秘密生成（走 setup.yaml 字段声明）

def _generate(field: dict) -> str:
    kind, length = field.get("generate", "token"), int(field.get("generate_length") or 32)
    if kind == "hex":
        return secrets.token_hex((length + 1) // 2)[:length]
    if kind == "password":
        alphabet = string.ascii_letters + string.digits  # 避免符号在 env/compose/shell 间转义踩坑
        return "".join(secrets.choice(alphabet) for _ in range(length))
    return secrets.token_urlsafe(length)[:length]


def generate_env(closure: dict, workdir: Path, http_port: int, host_root: str = "") -> Path:
    """按 setup.yaml 字段声明生成一次性测试 env；秘密字段随机，普通字段用默认值。

    host_root：CI 场景（Jenkins agent 容器内经 docker.sock 操作宿主 dockerd）下，
    工作区路径在宿主视角的真实前缀；所有作为卷挂载源/构建上下文的值须翻译，
    否则 dockerd 在宿主上找不到路径、静默挂空目录。"""
    install_root = PROFILE.install_root.resolve().as_posix()

    def host_path(p: Path) -> str:
        s = p.resolve().as_posix()
        if host_root and s.startswith(install_root):
            s = host_root.rstrip("/").replace("\\", "/") + s[len(install_root):]
        return s

    values = {
        "TZ": "Asia/Shanghai",
        "BASE_DOMAIN": "localhost",
        "HTTP_PORT": str(http_port),
        "DATA_ROOT": host_path(workdir / "data"),
        "REPO_ROOT": host_path(PROFILE.install_root),
        "COMPONENTS_ROOT": host_path(Cfg.COMPONENTS_DIR),
    }
    for comp in closure.values():
        for field in comp["setup"].get("fields") or []:
            key = field.get("key", "")
            if not key or key in values:
                continue  # 先声明优先：多组件共用的秘密（如 POSTGRES_PASSWORD）保持同一值
            if field.get("kind") == "secret":
                values[key] = _generate(field)
            elif field.get("default") not in (None, ""):
                values[key] = str(field["default"])
    # jenkins compose 挂载 ${SSH_KEY_PATH}:/run/ssh/id_rsa:ro，文件必须存在；沙箱给个哑文件
    dummy_key = workdir / "dummy-ssh-key"
    dummy_key.write_text("sandbox-placeholder-key\n", encoding="utf-8")
    values.setdefault("SSH_KEY_PATH", host_path(dummy_key))

    env_path = workdir / "sandbox.env"
    env_path.write_text("\n".join(f"{k}={v}" for k, v in sorted(values.items())) + "\n",
                        encoding="utf-8", newline="\n")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass
    missing = required_vars(closure) - set(values)
    if missing:
        raise SystemExit(f"以下必需变量未被 setup.yaml 字段覆盖，无法生成沙箱 env：{sorted(missing)}")
    return env_path


def required_vars(closure: dict) -> set:
    """从 compose 文本提取 ${VAR} / ${VAR:?} 引用（生成完备性自检用）"""
    found = set()
    for comp in closure.values():
        found |= set(ENV_VAR.findall(comp["compose"].read_text(encoding="utf-8")))
    # 这些由沙箱底座固定提供或 compose 内有 :- 兜底，无需字段覆盖
    provided = {"TZ", "BASE_DOMAIN", "HTTP_PORT", "DATA_ROOT", "REPO_ROOT", "COMPONENTS_ROOT",
                "SSH_KEY_PATH", "HTTP_PROXY", "HTTPS_PROXY"}
    return {v for v in found if v not in provided}


# ---------------------------------------------------------------- compose 隔离改写

def transform_compose(comp: dict, out_dir: Path) -> Path:
    """改写组件 compose：项目内建网络 + 剥离宿主端口（入口 caddy 除外）+ 剔除逃逸到生产的 extra_hosts"""
    doc = yaml.safe_load(comp["compose"].read_text(encoding="utf-8")) or {}
    for svc_name, svc in (doc.get("services") or {}).items():
        svc.pop("restart", None)  # 沙箱容器不得有重启策略：停止即终态，防止销毁阶段复活
        if comp["sandbox_env"]:  # 组件自述的沙箱专用环境覆盖（plugin.yaml sandbox.env）
            env = svc.setdefault("environment", {})
            if isinstance(env, dict):
                env.update(comp["sandbox_env"])
        if comp["name"] != ENTRY_COMPONENT:
            svc.pop("ports", None)  # 沙箱内不需要宿主端口；探针经入口 caddy 按 Host 头进入
        hosts = svc.get("extra_hosts") or []
        kept = [h for h in hosts if not str(h).split(":")[0].endswith(".localhost")]
        if kept:
            svc["extra_hosts"] = kept
        else:
            svc.pop("extra_hosts", None)
    # external 共享网络 aisystem → 项目内建网络（chronicle-sandbox_default）
    doc["networks"] = {"default": {}}
    out = out_dir / f"{comp['name']}.yml"
    out.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                   encoding="utf-8", newline="\n")
    return out


# ---------------------------------------------------------------- docker 编排

class Compose:
    def __init__(self, files: list[Path], env_path: Path, scrub: set[str]):
        self.base = ["docker", "compose", "-p", PROJECT, "--env-file", str(env_path)]
        for f in files:
            self.base += ["-f", str(f)]
        # 隔离关键：chronicler 的 config._load_dotenv 在 import 时把生产 .env 注入进程环境，
        # 而 compose 插值优先级是「进程环境 > --env-file」——不清洗的话生产值（如 HTTP_PORT=80）
        # 会静默覆盖沙箱 env，沙箱容器直接绑到生产端口。凡 compose 引用的变量一律从子进程环境剔除，
        # 只由 --env-file 唯一供给。
        self.env = {k: v for k, v in os.environ.items() if k not in scrub}
        self.logs: list[str] = []

    def run(self, *args, timeout: int = 600, check: bool = True) -> subprocess.CompletedProcess:
        r = subprocess.run([*self.base, *args], capture_output=True, env=self.env,
                           encoding="utf-8", errors="replace", timeout=timeout)
        tail = (r.stdout + r.stderr).strip()
        if tail:
            self.logs.append(tail[-400:])
        if check and r.returncode != 0:
            raise RuntimeError(f"compose {' '.join(args)} 失败：{tail[-300:]}")
        return r

    def container_state(self, service: str) -> str:
        r = subprocess.run(
            ["docker", "inspect", "-f",
             "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
             f"{PROJECT}-{service}-1"],
            capture_output=True, encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else "absent"


def wait_ready(compose: Compose, service: str, readiness: dict, default_timeout: int) -> tuple[bool, str]:
    """container-health：等 healthy（无健康检查则 running）；process：running 即可"""
    kind = (readiness or {}).get("kind", "container-health")
    timeout = int((readiness or {}).get("timeout_sec") or default_timeout)
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = compose.container_state(service)
        if "exited" in state or "dead" in state:
            return False, state
        if kind == "process" and "running" in state:
            return True, state
        if "healthy" in state or state == "running":
            return True, state
        time.sleep(5)
    return False, f"超时（{timeout}s）：{compose.container_state(service)}"


# ---------------------------------------------------------------- 可达性探针

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def probe_once(url: str, http_port: int, expect: set, probe_host: str = "127.0.0.1") -> dict:
    m = re.match(r"https?://([^/]+)(/.*)?$", url)
    host, path = m.group(1), m.group(2) or "/"
    if not host.endswith(".localhost"):
        return {"ok": False, "detail": f"非本机域名，无法经沙箱入口探测：{host}"}
    # probe_host：本机直跑用 127.0.0.1；CI agent 容器内用 host.docker.internal（指宿主 dockerd）
    req = urllib.request.Request(f"http://{probe_host}:{http_port}{path}", headers={"Host": host})
    try:
        resp = urllib.request.build_opener(_NoRedirect).open(req, timeout=8)
        code, loc = resp.status, ""
    except urllib.error.HTTPError as e:
        code, loc = e.code, e.headers.get("Location", "") or ""
    except Exception as e:
        return {"ok": False, "detail": f"不可达（{type(e).__name__}: {e}）"}
    sso = " →SSO" if "sso.localhost" in loc else ""
    ok = code in expect
    return {"ok": ok, "detail": f"{host}{path} -> {code}{sso}"
            + ("" if ok else f"（期望 {sorted(expect)}）"), "code": code}


def probe_all(targets: list[dict], http_port: int, deadline: float,
              probe_host: str = "127.0.0.1") -> list[dict]:
    """整体重试：慢启动组件（如 mkdocs 运行时装依赖）在预算内反复探测"""
    results = {t["name"]: {"name": t["name"], "url": t["url"], "ok": False,
                           "detail": "未探测"} for t in targets}
    pending = {t["name"]: t for t in targets}
    while pending and time.time() < deadline:
        for name, t in list(pending.items()):
            expect = set(t["probe"].get("expect") or DEFAULT_OK_CODES)
            r = probe_once(t["url"], http_port, expect, probe_host)
            if r["ok"]:
                results[name].update(r)
                del pending[name]
            else:
                results[name]["detail"] = r["detail"]
        if pending:
            time.sleep(3)
    for name in pending:
        results[name]["detail"] += "（探测预算耗尽）"
    return [results[t["name"]] for t in targets]


def force_cleanup():
    """兑底清理：按 compose 项目标签强删残留容器与网络（down 不完整时的保险）"""
    r = subprocess.run(["docker", "ps", "-aq", "--filter",
                        f"label=com.docker.compose.project={PROJECT}"],
                       capture_output=True, encoding="utf-8", errors="replace")
    ids = r.stdout.split()
    if ids:
        print(f"[sandbox] 强制清理残留容器：{len(ids)} 个")
        subprocess.run(["docker", "rm", "-f", *ids],
                       capture_output=True, encoding="utf-8", errors="replace")
    subprocess.run(["docker", "network", "rm", f"{PROJECT}_default"],
                   capture_output=True, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- JUnit 报告

def write_junit(path: Path, results: list[dict], skipped: list[dict], elapsed: float):
    cases = []
    failures = 0
    for r in results:
        if r["ok"]:
            cases.append(f'  <testcase name="{xml_escape(r["name"])}" classname="sandbox-reachability"/>')
        else:
            failures += 1
            cases.append(f'  <testcase name="{xml_escape(r["name"])}" classname="sandbox-reachability">'
                         f'<failure message="{xml_escape(r["detail"])}"/></testcase>')
    for s in skipped:
        cases.append(f'  <testcase name="{xml_escape(s["name"])}" classname="sandbox-reachability">'
                     f'<skipped message="{xml_escape(s["reason"])}"/></testcase>')
    path.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="sandbox-reachability" tests="{len(cases)}" failures="{failures}" '
        f'skipped="{len(skipped)}" time="{elapsed:.1f}">\n' + "\n".join(cases) + "\n</testsuite>\n",
        encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- 主流程

def run_sandbox(args) -> int:
    started = time.time()
    components = load_components()

    # 目标：docker 组件中有 url 的；enabled: false 的默认跳过
    skipped, targets = [], []
    for comp in components.values():
        if comp["driver"] != "docker" or not comp["url"]:
            continue
        if args.components and comp["name"] not in args.components:
            skipped.append({"name": comp["name"], "reason": "未在 --components 指定"})
            continue
        if not comp["enabled"] and not args.include_disabled and not args.components:
            skipped.append({"name": comp["name"], "reason": "plugin.yaml enabled: false"})
            continue
        targets.append(comp)
    if args.components:
        unknown = set(args.components) - {c["name"] for c in components.values()}
        if unknown:
            raise SystemExit(f"未知组件：{sorted(unknown)}")

    waves = resolve_closure([t["name"] for t in targets], components)
    closure = {n: components[n] for w in waves for n in w}
    print(f"[sandbox] 目标组件：{[t['name'] for t in targets]}")
    print(f"[sandbox] 启动波浪：{waves}")

    # 端口可用性前置检查（Windows Hyper-V 排除区间等占用要早发现）；0 = 由系统分配空闲端口
    if args.http_port == 0:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            args.http_port = s.getsockname()[1]
    else:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", args.http_port))
            except OSError as e:
                raise SystemExit(f"沙箱入口端口 {args.http_port} 不可用：{e}；请用 --http-port 换一个")

    workdir = Path(args.workdir).resolve() if args.workdir else Path(
        tempfile.mkdtemp(prefix="chronicle-sandbox-"))
    workdir.mkdir(parents=True, exist_ok=True)
    compose_dir = workdir / "compose"
    compose_dir.mkdir(exist_ok=True)
    print(f"[sandbox] 工作目录：{workdir}")

    compose = None
    results = None
    error = None
    try:
        env_path = generate_env(closure, workdir, args.http_port, args.host_root)
        files = [transform_compose(comp, compose_dir) for comp in closure.values()]
        scrub = BASE_ENV_KEYS | set()
        for comp in closure.values():
            scrub |= set(ENV_VAR_ALL.findall(comp["compose"].read_text(encoding="utf-8")))
        compose = Compose(files, env_path, scrub)
        if os.environ.get("SANDBOX_DEBUG"):
            cfg = compose.run("config", check=False)
            print("[sandbox:debug] cmd:", " ".join(compose.base))
            print("[sandbox:debug] config 渲染片段:", [l for l in (cfg.stdout + "").splitlines() if "published" in l or "HTTP_PORT" in l][:5])

        if not args.skip_pull:
            print("[sandbox] 拉取镜像（build 型组件由 up 按需构建）...")
            compose.run("pull", "--ignore-buildable", "--ignore-pull-failures",
                        timeout=args.timeout, check=False)

        for wave in waves:
            print(f"[sandbox] 启动：{wave}")
            compose.run("up", "-d", *wave, timeout=args.timeout)
            for service in wave:
                readiness = closure[service]["setup"].get("readiness") or {}
                ok, state = wait_ready(compose, service, readiness, args.timeout)
                print(f"[sandbox]   {service}: {'就绪' if ok else '未就绪'} ({state})")
                if not ok:
                    raise RuntimeError(f"组件 {service} 就绪失败：{state}\n"
                                       f"最近日志：{compose.logs[-1] if compose.logs else '(无)'}")

        print("[sandbox] 探测组件入口...")
        results = probe_all(targets, args.http_port, time.time() + args.probe_timeout,
                            args.probe_host)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        error = str(e)
    finally:
        if compose is not None and not args.keep:
            print("[sandbox] 销毁沙箱（down -v）...")
            try:
                compose.run("down", "-v", "--remove-orphans", timeout=600, check=False)
            except Exception as e:
                print(f"[sandbox] down 异常（转入强制清理）：{e}", file=sys.stderr)
            force_cleanup()  # down 超时/失败亦不许残留：按 compose 项目标签兜底清除
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            print(f"[sandbox] --keep：沙箱保留，工作目录 {workdir}")

    elapsed = time.time() - started
    if error:
        print(f"\n[sandbox] 失败：{error}", file=sys.stderr)
        if args.junit:
            write_junit(Path(args.junit),
                        [{"name": t["name"], "url": t["url"], "ok": False, "detail": error}
                         for t in targets], skipped, elapsed)
        return 2
    failed = 0
    print("\n===== 沙箱可达性结果 =====")
    for r in results:
        mark = "[PASS]" if r["ok"] else "[FAIL]"
        print(f"{mark} {r['name']:18s} {r['detail']}")
        failed += 0 if r["ok"] else 1
    for s in skipped:
        print(f"[SKIP] {s['name']:18s} {s['reason']}")
    print(f"\n{len(results) - failed}/{len(results)} 通过，{len(skipped)} 跳过，耗时 {elapsed:.0f}s")
    if args.junit:
        write_junit(Path(args.junit), results, skipped, elapsed)
        print(f"[sandbox] JUnit 报告：{args.junit}")
    return 1 if failed else 0


def main(argv: list[str] | None = None):
    p = argparse.ArgumentParser(prog="python -m chronicler sandbox",
                                description="隔离沙箱内现拉现建现测现毁的组件入口可达性测试")
    p.add_argument("--components", nargs="+", help="只测指定组件（依赖与入口自动带上）")
    p.add_argument("--include-disabled", action="store_true",
                   help="同时测 plugin.yaml enabled: false 的组件")
    p.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT, help="沙箱 caddy 入口端口")
    p.add_argument("--timeout", type=int, default=600, help="单组件就绪/单步 compose 超时秒数")
    p.add_argument("--probe-timeout", type=int, default=300, help="全部探针的整体重试预算秒数")
    p.add_argument("--workdir", help="沙箱工作目录（默认系统临时目录；CI 中应指向 workspace 内）")
    p.add_argument("--host-root", default="",
                   help="工作区在宿主 dockerd 视角的真实路径前缀（CI docker.sock 场景必传）")
    p.add_argument("--probe-host", default="127.0.0.1",
                   help="探针目标主机（CI agent 容器内用 host.docker.internal）")
    p.add_argument("--keep", action="store_true", help="测完不销毁（调试用）")
    p.add_argument("--skip-pull", action="store_true", help="跳过 docker compose pull")
    p.add_argument("--junit", help="JUnit XML 报告输出路径")
    sys.exit(run_sandbox(p.parse_args(argv)))

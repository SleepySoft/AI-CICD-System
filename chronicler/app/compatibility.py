"""只读版本与契约检查：报告 gap，不迁移、不重建、不读取秘密值。"""
import hashlib
import sqlite3
import subprocess
from pathlib import Path

import yaml

from chronicler import __version__

from .config import Cfg
from .runtime import PROFILE
from .initialization.catalog import CatalogError, validate

SHADOW_REQUIRED_TEMPLATES = ("cognitive-state.yaml", "requirement.md", "adr.md",
                             "know-how.md", "assessment.md", "run-record.md")


def _issue(scope: str, name: str, code: str, message: str) -> dict:
    return {"scope": scope, "name": name, "code": code, "message": message}


def _yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("文件内容必须是 YAML 映射")
    return value


def _shadow_governance_revision(root: Path) -> str:
    """治理正文和全部资产模板的内容修订；状态中的项目基线不参与比较。"""
    central = PROFILE.resource_root / "assets" / "shadow-project"
    if any(not (central / "templates" / name).is_file() for name in SHADOW_REQUIRED_TEMPLATES):
        raise ValueError("中央 Shadow 模板缺少必要资产模板")
    templates = [p.relative_to(central) for p in (central / "templates").glob("*") if p.is_file()]
    files = [root / "SKILL.md", *(root / path for path in templates)]
    if not templates or any(not path.is_file() for path in files):
        raise ValueError("Shadow 治理正文或资产模板缺失")
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _component_checks() -> tuple[list[dict], list[dict]]:
    components, issues = [], []
    names = set()
    for base in (Cfg.COMPONENTS_DIR, Cfg.DATA / "components"):
        if base.is_dir():
            names.update(child.name for child in base.iterdir() if child.is_dir())
    for name in sorted(names):
        root = (Cfg.DATA / "components" / name)
        if not root.is_dir():
            root = Cfg.COMPONENTS_DIR / name
        plugin_path, setup_path = root / "plugin.yaml", root / "setup.yaml"
        entry = {"name": name, "source": "override" if root.parent == Cfg.DATA / "components" else "builtin",
                 "definition_revision": "", "setup_schema_version": None, "deployed_revision": None,
                 "status": "definition-valid/runtime-unverified"}
        try:
            if not plugin_path.is_file() or not setup_path.is_file():
                missing = [p.name for p in (plugin_path, setup_path) if not p.is_file()]
                raise ValueError("缺少组件声明：" + "、".join(missing))
            plugin, setup = _yaml(plugin_path), _yaml(setup_path)
            if plugin.get("name") != name:
                raise ValueError("plugin.yaml 的 name 与目录名不一致")
            entry["setup_schema_version"] = setup.get("schema_version")
            validate(name, setup, root)
            hook = setup.get("initialize_hook")
            if hook and not (root / hook).is_file():
                raise ValueError("initialize_hook 声明的文件不存在")
            files = [p for p in (plugin_path, setup_path, root / "compose.yml", root / "SKILL.md") if p.is_file()]
            hooks = root / "hooks"
            if hooks.is_dir():
                files.extend(p for p in hooks.rglob("*") if p.is_file() and p.suffix == ".py")
            digest = hashlib.sha256()
            for path in sorted(files):
                digest.update(str(path.relative_to(root)).encode("utf-8"))
                digest.update(b"\0")
                digest.update(path.read_bytes())
                digest.update(b"\0")
            entry["definition_revision"] = digest.hexdigest()[:16]
        except yaml.YAMLError:
            entry["status"] = "gap"
            issues.append(_issue("component", name, "contract_invalid", "组件 YAML 格式无效"))
        except (OSError, ValueError, CatalogError) as exc:
            entry["status"] = "gap"
            issues.append(_issue("component", name, "contract_invalid", str(exc)))
        components.append(entry)
    return components, issues


def shadow_version_gap(dest: Path, expected_version: str, expected_schema: int) -> tuple[dict, str]:
    """检查版本、状态结构和治理内容修订；不自动覆盖项目文件。"""
    versions = {"skill_version": None, "schema_version": None, "governance_revision": None}
    try:
        state = _yaml(dest / ".cognitive-state.yaml")
        first = (dest / "SKILL.md").read_text(encoding="utf-8").split("---", 2)
        if len(first) < 3 or first[0].strip():
            raise ValueError("SKILL.md 缺少 YAML 元数据")
        skill = yaml.safe_load(first[1])
        if not isinstance(skill, dict):
            raise ValueError("SKILL.md 元数据无效")
        versions.update(skill_version=state.get("skill_version"), schema_version=state.get("schema_version"))
        if (state.get("skill_version") != skill.get("skill_version") or
                state.get("schema_version") != skill.get("schema_version")):
            raise ValueError("状态文件与 SKILL.md 版本不一致")
        if str(versions["skill_version"]) != expected_version or versions["schema_version"] != expected_schema:
            raise ValueError(f"工作区版本 {versions['skill_version']}/schema {versions['schema_version']}"
                             f" 与模板 {expected_version}/schema {expected_schema} 不一致；需显式评估迁移")
        for section, fields in (("source", ("repository", "branch", "commit")),
                                ("maintenance", ("completed_at", "last_run", "status"))):
            value = state.get(section)
            if not isinstance(value, dict) or any(field not in value for field in fields):
                raise ValueError(f"状态文件缺少 {section} 必需字段")
        if not isinstance(state["source"]["commit"], str) or not isinstance(state["maintenance"]["status"], str):
            raise ValueError("状态文件字段类型错误")
        expected_revision = _shadow_governance_revision(PROFILE.resource_root / "assets" / "shadow-project")
        versions["governance_revision"] = _shadow_governance_revision(dest)
        if versions["governance_revision"] != expected_revision:
            raise ValueError(f"治理内容修订 {versions['governance_revision']} 与当前模板"
                             f" {expected_revision} 不一致；需审阅 SKILL 和资产模板")
    except yaml.YAMLError:
        return versions, "Shadow YAML 格式无效"
    except (OSError, ValueError) as exc:
        return versions, str(exc)
    return versions, ""


def _shadow_checks() -> tuple[dict, list[dict], list[dict]]:
    template = PROFILE.resource_root / "assets" / "shadow-project"
    issues, workspaces = [], []
    try:
        expected_skill = _yaml(template / ".cognitive-state.yaml")
        expected_version = str(expected_skill["skill_version"])
        expected_schema = expected_skill["schema_version"]
        expected_revision = _shadow_governance_revision(template)
        _, template_gap = shadow_version_gap(template, expected_version, expected_schema)
        if template_gap:
            raise ValueError(template_gap)
        required = [Path("SKILL.md"), Path(".cognitive-state.yaml"), Path("README.md")]
        required += [p.relative_to(template) for p in (template / "templates").glob("*") if p.is_file()]
    except (OSError, yaml.YAMLError, ValueError, KeyError) as exc:
        return {"skill_version": None, "schema_version": None, "governance_revision": None}, [], [
            _issue("shadow-template", "builtin", "template_invalid", type(exc).__name__)]
    db_path = Cfg.db_path()
    if not db_path.is_file():
        return {"skill_version": expected_version, "schema_version": expected_schema,
                "governance_revision": expected_revision}, [], issues
    try:
        conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            projects = conn.execute("SELECT name FROM projects ORDER BY name").fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"skill_version": expected_version, "schema_version": expected_schema,
                "governance_revision": expected_revision}, [], [
            _issue("workspace", "projects", "database_unreadable", type(exc).__name__)]
    for (name,) in projects:
        dest = Cfg.PUBLIC / "shadow" / f"{name}-shadow"
        entry = {"name": name, "path": str(dest), "skill_version": None,
                 "schema_version": None, "governance_revision": None, "status": "ok"}
        if not dest.exists():
            entry["status"] = "uninitialized"
            workspaces.append(entry)
            continue  # Shadow 按需创建；缺目录不是损坏。
        try:
            result = subprocess.run(["git", "-C", str(dest), "rev-parse", "--show-toplevel"],
                                    capture_output=True, encoding="utf-8", errors="replace", timeout=10)
            if result.returncode or Path(result.stdout.strip()).resolve() != dest.resolve():
                raise ValueError("不是独立 Git 仓库")
            missing = [str(p) for p in required if not (dest / p).is_file()]
            if missing:
                raise ValueError("缺少治理资源：" + "、".join(missing))
            versions, gap = shadow_version_gap(dest, expected_version, expected_schema)
            entry.update(versions)
            if gap:
                raise ValueError(gap)
        except yaml.YAMLError:
            entry["status"] = "gap"
            issues.append(_issue("workspace", name, "shadow_contract_gap", "Shadow YAML 格式无效"))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            entry["status"] = "gap"
            issues.append(_issue("workspace", name, "shadow_contract_gap", str(exc)))
        workspaces.append(entry)
    return {"skill_version": expected_version, "schema_version": expected_schema,
            "governance_revision": expected_revision}, workspaces, issues


def check() -> dict:
    """返回有效声明版本、工作区版本及可操作的 gap；调用期间不写入数据。"""
    components, component_issues = _component_checks()
    template, workspaces, workspace_issues = _shadow_checks()
    issues = component_issues + workspace_issues
    return {"product_version": __version__, "components": components,
            "shadow_template": template, "workspaces": workspaces,
            "issues": issues, "ok": not issues}

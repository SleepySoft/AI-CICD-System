"""Prompt 标准运行上下文构建与渲染（FR-MGR-031，ADR-0049）。

上下文由本次 Run、源仓、Shadow 仓、基线、变化和 harness 事实统一构造；
Prompt 只声明正文实际使用的标准字段，运行时注入完整契约上下文。
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import projects, registry
from .db import q1

CONTEXT_SCHEMA_VERSION = "1"
PLACEHOLDER_RE = re.compile(r"\{\{([a-z_][a-z0-9_]*)\}\}")

CONTEXT_FIELDS = (
    "context_schema_version",
    "run_id", "task_id", "task_type", "task_mode", "trigger_kind", "run_actor",
    "run_date", "run_started_at", "run_timezone",
    "project_id", "project_name",
    "source_repo_dir", "source_repo_url", "source_default_branch", "source_branch",
    "source_head_commit", "source_dirty",
    "source_synced_at", "source_sync_error",
    "baseline_run_id", "baseline_source_commit", "baseline_run_finished_at",
    "baseline_record_file",
    "change_policy", "change_state", "change_summary_json", "change_context",
    "shadow_repo_dir", "shadow_repo_url", "shadow_head_commit", "shadow_dirty",
    "shadow_source_baseline_commit", "shadow_last_run_file", "shadow_state_error",
    "harness_name", "harness_report_mode", "harness_cwd", "harness_timeout_sec",
    "report_delivery",
    "run_dir", "report_file", "prompt_file", "log_file",
    "prompt_name", "prompt_version", "prompt_hash",
    "components", "components_json", "ci_url", "ci_context_json",
    "extra",
    "task_period_start", "task_period_end", "task_period_timezone",
)


def _text(value) -> str:
    return "" if value is None else str(value)


def _iso_timestamp(value) -> str:
    if value in (None, "", 0):
        return ""
    try:
        moment = datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone()
    except (TypeError, ValueError, OSError):
        return ""
    return moment.isoformat(timespec="seconds")


def _local_timestamp(moment: float) -> datetime:
    return datetime.fromtimestamp(moment, tz=timezone.utc).astimezone()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _components_context() -> tuple[str, list[dict]]:
    components = registry.injectable_components()
    if not components:
        text = "- （未注入任何组件能力；按纯本地仓库分析，缺失维度如实说明）"
    else:
        text = "\n".join(
            f"- {item['name']}: {item['desc']}（能力详情见 SKILL 文件：{item['skill']}，需要时再读）"
            for item in components
        )
    return text, components


def _shadow_state(path: Path) -> tuple[str, str, str]:
    state_path = path / ".cognitive-state.yaml"
    if not state_path.is_file():
        return "", "", "Shadow 状态文件不存在"
    try:
        data = yaml.safe_load(state_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("状态文件根节点不是对象")
        source = data.get("source") or {}
        maintenance = data.get("maintenance") or {}
        return (_text(source.get("commit", "")), _text(maintenance.get("last_run", "")), "")
    except Exception as exc:  # noqa: BLE001 - 状态异常必须显式进入上下文
        return "", "", f"Shadow 状态读取失败：{type(exc).__name__}"


def build_prompt_context(*, run_id: int, project: dict, task_type: str, task_mode: str,
                         task_id: int | None, trigger_kind: str, actor: str, started_at: float,
                         harness: dict, harness_name: str, cwd: str, change: dict,
                         ci_context: dict, prompt_name: str, prompt_version: str, prompt_hash: str,
                         run_dir: Path, report_file: str, prompt_file: str, report_delivery: str,
                         change_policy: str, extra: str = "", task_period_start: str = "",
                         task_period_end: str = "", task_period_timezone: str = "") -> dict[str, str]:
    """构造契约 v1 的全部标准字段；缺失事实用空字符串显式表达。"""
    shadow_dir = projects.ensure_shadow_repo(project["id"])
    current_project = projects.get_project(project["id"])
    components, component_list = _components_context()
    baseline_commit, last_run_file, state_error = _shadow_state(shadow_dir)
    baseline_run_id = change.get("baseline_run_id")
    baseline_row = None
    if baseline_run_id is not None:
        baseline_row = q1("SELECT id, finished_at, report_path FROM task_runs WHERE id=?",
                          (baseline_run_id,))

    started = _local_timestamp(started_at)
    summary = change.get("change_summary") or {}
    context = {
        "context_schema_version": CONTEXT_SCHEMA_VERSION,
        "run_id": str(run_id),
        "task_id": _text(task_id),
        "task_type": task_type,
        "task_mode": task_mode,
        "trigger_kind": trigger_kind,
        "run_actor": actor,
        "run_date": started.strftime("%Y-%m-%d"),
        "run_started_at": started.isoformat(timespec="seconds"),
        "run_timezone": started.tzname() or started.strftime("%z"),
        "project_id": str(project["id"]),
        "project_name": current_project["name"],
        "source_repo_dir": str(projects.repo_dir(project["id"])),
        "source_repo_url": current_project["git_url"],
        "source_default_branch": current_project.get("default_branch") or "",
        "source_branch": projects.current_branch(project["id"]),
        "source_head_commit": projects.head_commit(project["id"]),
        "source_dirty": "true" if projects.repo_dirty(project["id"]) else "false",
        "source_synced_at": _iso_timestamp(current_project.get("last_synced_at")),
        "source_sync_error": current_project.get("last_sync_error") or "",
        "baseline_run_id": _text(baseline_run_id),
        "baseline_source_commit": summary.get("base_revision") or "",
        "baseline_run_finished_at": _iso_timestamp(
            baseline_row.get("finished_at") if baseline_row else None),
        "baseline_record_file": (baseline_row or {}).get("report_path") or "",
        "change_policy": change_policy,
        "change_state": summary.get("state") or "",
        "change_summary_json": _json(summary),
        "change_context": _text(change.get("formatted_context", "")),
        "shadow_repo_dir": str(shadow_dir),
        "shadow_repo_url": current_project.get("shadow_repo") or "",
        "shadow_head_commit": projects.shadow_head(project["id"]),
        "shadow_dirty": "true" if projects.shadow_dirty(project["id"]) else "false",
        "shadow_source_baseline_commit": baseline_commit,
        "shadow_last_run_file": last_run_file,
        "shadow_state_error": state_error,
        "harness_name": harness_name,
        "harness_report_mode": harness.get("report_mode") or "file",
        "harness_cwd": cwd,
        "harness_timeout_sec": str(int(harness.get("timeout_sec", 1800))),
        "report_delivery": report_delivery,
        "run_dir": str(run_dir),
        "report_file": report_file,
        "prompt_file": prompt_file,
        "log_file": str(Path(run_dir) / "run.log"),
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "components": components,
        "components_json": _json(component_list),
        "ci_url": current_project.get("ci_url") or "",
        "ci_context_json": _json(ci_context),
        "extra": extra,
        "task_period_start": task_period_start,
        "task_period_end": task_period_end,
        "task_period_timezone": task_period_timezone,
    }
    if set(context) != set(CONTEXT_FIELDS):
        raise RuntimeError("Prompt 上下文字段与契约不一致")
    return {key: _text(value) for key, value in context.items()}


def render_prompt(template: str, context: dict[str, str]) -> str:
    """替换标准字段；未识别或未填充的占位符会显式失败，避免 Prompt 带着空槽启动。"""
    unknown = sorted({item for item in PLACEHOLDER_RE.findall(template)
                      if item not in context})
    if unknown:
        raise RuntimeError(f"Prompt 使用了未注入上下文字段：{', '.join(unknown)}")
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    unresolved = sorted(set(PLACEHOLDER_RE.findall(rendered)))
    if unresolved:
        raise RuntimeError(f"Prompt 存在未填充占位符：{', '.join(unresolved)}")
    return rendered

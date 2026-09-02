"""有效输入快照与增量判断（FR-MGR-027/028，ADR-0035）。"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

from fastapi import HTTPException

from . import projects
from .db import q

CHANGE_POLICIES = ("always", "repo-changed", "inputs-changed")


def normalize_probes(probes) -> list[dict]:
    if probes in (None, ""):
        return []
    if isinstance(probes, str):
        try:
            probes = json.loads(probes)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="change_probes 不是合法 JSON") from exc
    if not isinstance(probes, list):
        raise HTTPException(status_code=422, detail="change_probes 必须是数组")
    cleaned = []
    names = set()
    for item in probes:
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="每个 change probe 必须是对象")
        name = str(item.get("name", "")).strip()
        command = str(item.get("command", "")).strip()
        if not name or not command:
            raise HTTPException(status_code=422, detail="change probe 的 name 和 command 不能为空")
        if name in names:
            raise HTTPException(status_code=422, detail=f"change probe 名称重复：{name}")
        try:
            timeout_sec = int(item.get("timeout_sec", 60))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"probe {name} timeout_sec 必须是整数") from exc
        if timeout_sec <= 0 or timeout_sec > 600:
            raise HTTPException(status_code=422, detail=f"probe {name} timeout_sec 必须在 1~600 秒")
        names.add(name)
        cleaned.append({"name": name, "command": command, "timeout_sec": timeout_sec})
    return cleaned


def _baseline(project_id: int, task_type: str, task_id: int | None) -> dict | None:
    if task_id is not None:
        rows = q("SELECT id, input_snapshot FROM task_runs"
                 " WHERE task_id=? AND status='success' ORDER BY id DESC LIMIT 1", (task_id,))
    else:
        rows = q("SELECT id, input_snapshot FROM task_runs"
                 " WHERE project_id=? AND task_type=? AND status='success'"
                 " ORDER BY id DESC LIMIT 1", (project_id, task_type))
    if not rows:
        return None
    row = rows[0]
    try:
        row["input_snapshot"] = json.loads(row.get("input_snapshot") or "{}")
    except json.JSONDecodeError:
        row["input_snapshot"] = {}
    return row


def _git_change(repo: Path, base: str, head: str) -> dict:
    result = {"state": "initial" if not base else "unknown", "base_revision": base,
              "head_revision": head, "commits": 0, "files": 0,
              "insertions": 0, "deletions": 0, "commit_preview": [], "error": ""}
    if not head:
        result.update(state="unknown", error="无法读取当前 Git revision")
        return result
    if not base:
        return result
    if base == head:
        result["state"] = "unchanged"
        return result
    exists = projects._git(["-C", str(repo), "cat-file", "-e", f"{base}^{{commit}}"])
    if exists.returncode != 0:
        result.update(state="unknown", error="基线提交不在当前克隆中")
        return result
    ancestor = projects._git(["-C", str(repo), "merge-base", "--is-ancestor", base, head])
    if ancestor.returncode == 1:
        result["state"] = "diverged"
        return result
    if ancestor.returncode != 0:
        result.update(state="unknown", error=ancestor.stderr.strip()[:300])
        return result
    result["state"] = "changed"
    count = projects._git(["-C", str(repo), "rev-list", "--count", f"{base}..{head}"])
    if count.returncode == 0 and count.stdout.strip().isdigit():
        result["commits"] = int(count.stdout.strip())
    stat = projects._git(["-C", str(repo), "diff", "--numstat", base, head])
    if stat.returncode == 0:
        for line in stat.stdout.splitlines():
            added, deleted, *_ = line.split("\t", 2)
            result["files"] += 1
            result["insertions"] += int(added) if added.isdigit() else 0
            result["deletions"] += int(deleted) if deleted.isdigit() else 0
    preview = projects._git(["-C", str(repo), "log", "-10", "--format=%h %s", f"{base}..{head}"])
    if preview.returncode == 0:
        result["commit_preview"] = preview.stdout.splitlines()
    return result


def _run_probe(repo: Path, probe: dict) -> dict:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        completed = subprocess.run(probe["command"], shell=True, cwd=str(repo), env=env,
                                   capture_output=True, encoding="utf-8", errors="replace",
                                   timeout=probe["timeout_sec"])
        output = completed.stdout.strip()
        if completed.returncode != 0:
            return {"name": probe["name"], "status": "unknown", "fingerprint": "",
                    "error": f"probe 退出码 {completed.returncode}（stderr 未记录）"}
        if not output:
            return {"name": probe["name"], "status": "unknown", "fingerprint": "",
                    "error": "probe 未输出稳定标识"}
        return {"name": probe["name"], "status": "ok",
                "fingerprint": hashlib.sha256(output.encode()).hexdigest(), "error": ""}
    except subprocess.TimeoutExpired:
        return {"name": probe["name"], "status": "unknown", "fingerprint": "",
                "error": f"probe 超时（{probe['timeout_sec']}s）"}
    except Exception as exc:  # noqa: BLE001 - 探测失败必须进入快照而非中断任务
        return {"name": probe["name"], "status": "unknown", "fingerprint": "",
                "error": f"probe 执行异常：{type(exc).__name__}（详情未记录）"}


def capture(project_id: int, task_type: str, task_id: int | None = None,
            probes=None) -> dict:
    repo = projects.repo_dir(project_id)
    baseline = _baseline(project_id, task_type, task_id)
    previous = (baseline or {}).get("input_snapshot", {}).get("source_snapshot", {})
    base_revision = (previous.get("primary") or {}).get("revision", "")
    head_revision = projects.head_commit(project_id)
    git_change = _git_change(repo, base_revision, head_revision)
    current_probes = [_run_probe(repo, item) for item in normalize_probes(probes)]
    old_probes = {item.get("name"): item for item in previous.get("probes", [])}
    current_names = {item["name"] for item in current_probes}
    changed_probes = [item["name"] for item in current_probes
                      if item["status"] == "ok" and
                      old_probes.get(item["name"], {}).get("fingerprint") != item["fingerprint"]]
    changed_probes.extend(f"{name}（已移除）" for name in old_probes if name not in current_names)
    probe_errors = [f"{item['name']}: {item['error']}" for item in current_probes
                    if item["status"] != "ok"]
    if git_change["state"] == "unknown" or probe_errors:
        state = "unknown"
    elif git_change["state"] == "diverged":
        state = "diverged"
    elif git_change["state"] == "initial" or not baseline:
        state = "initial"
    elif git_change["state"] == "changed" or changed_probes:
        state = "changed"
    else:
        state = "unchanged"
    source = {"primary": {"kind": "git", "revision": head_revision},
              "probes": current_probes}
    fingerprint_data = {"primary": source["primary"],
                        "probes": [{"name": item["name"], "status": item["status"],
                                    "fingerprint": item["fingerprint"]} for item in current_probes]}
    source["fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"baseline_run_id": baseline["id"] if baseline else None,
            "source_snapshot": source,
            "change_summary": {**git_change, "state": state,
                       "baseline_run_id": baseline["id"] if baseline else None,
                               "repo_state": git_change["state"],
                               "changed_probes": changed_probes,
                               "probe_errors": probe_errors}}


def should_skip(policy: str, summary: dict) -> bool:
    if policy == "always":
        return False
    if summary.get("state") == "unknown" or summary.get("repo_state") == "unknown":
        return False
    if policy == "repo-changed":
        return summary.get("repo_state") == "unchanged"
    if policy == "inputs-changed":
        return summary.get("state") == "unchanged"
    raise HTTPException(status_code=422, detail=f"未知 change_policy：{policy}")


def format_context(summary: dict) -> str:
    state_labels = {"initial": "首次执行", "changed": "有增量", "unchanged": "无增量",
                    "diverged": "历史分叉", "unknown": "增量未知"}
    lines = [f"- 状态：{state_labels.get(summary.get('state'), summary.get('state', 'unknown'))}"]
    if summary.get("baseline_run_id"):
        lines.append(f"- 基线 Run：#{summary['baseline_run_id']}")
    lines.extend([
             f"- Git：{summary.get('base_revision') or '无基线'} → {summary.get('head_revision') or '未知'}",
             f"- 统计：{summary.get('commits', 0)} commits，{summary.get('files', 0)} files，"
             f"+{summary.get('insertions', 0)}/-{summary.get('deletions', 0)}"])
    if summary.get("changed_probes"):
        lines.append("- 外部输入变化：" + "、".join(summary["changed_probes"]))
    if summary.get("probe_errors") or summary.get("error"):
        lines.append("- 探测异常：" + "；".join(summary.get("probe_errors", []) +
                                               ([summary["error"]] if summary.get("error") else [])))
    if summary.get("commit_preview"):
        lines.append("- 提交预览：\n  - " + "\n  - ".join(summary["commit_preview"]))
    return "\n".join(lines)
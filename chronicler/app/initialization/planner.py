"""确定性初始化计划：方案展开、依赖闭包、冲突与稳定哈希。"""
import hashlib
import heapq
import json
import re

from . import catalog


class PlanError(ValueError):
    pass


def _selected(profile: str, explicit: list[str], entries: dict) -> tuple[set, dict]:
    if profile not in {"chronicler-only", "recommended", "full", "custom"}:
        raise PlanError("未知部署方案")
    selected = set(explicit if profile == "custom" else [])
    reasons = {name: "explicit" for name in selected}
    for name in selected:
        if name not in entries:
            raise PlanError(f"缺少组件或初始化声明：{name}")
        if entries[name]["component"].get("dependency_only"):
            raise PlanError(f"组件 {name} 只能由其他组件按依赖自动加入")
    if profile in {"recommended", "full"}:
        for name, entry in entries.items():
            if profile in entry["component"].get("profiles", []):
                selected.add(name)
                reasons[name] = "profile"
    queue = list(selected)
    heapq.heapify(queue)
    while queue:
        name = heapq.heappop(queue)
        if name not in entries:
            raise PlanError(f"缺少组件或初始化声明：{name}")
        for dep in sorted(entries[name]["component"].get("depends_on", [])):
            if dep not in selected:
                selected.add(dep)
                reasons[dep] = f"dependency-of:{name}"
                heapq.heappush(queue, dep)
    return selected, reasons


def _toposort(selected: set, entries: dict) -> list[str]:
    deps = {n: set(entries[n]["component"].get("depends_on", [])) & selected for n in selected}
    order = []
    while deps:
        ready = sorted(n for n, ds in deps.items() if not ds)
        if not ready:
            raise PlanError("组件依赖存在环")
        order.extend(ready)
        for n in ready:
            deps.pop(n)
        for ds in deps.values():
            ds.difference_update(ready)
    return order


def build(profile: str, explicit: list[str], values: dict, draft_revision: int,
          secret_presence: dict | None = None) -> dict:
    entries = catalog.load()
    selected, reasons = _selected(profile, explicit, entries)
    current = catalog.current_platform()
    for name in selected:
        entry = entries[name]
        if entry["error"]:
            raise PlanError(f"{name}: {entry['error']}")
        comp = entry["component"]
        if current not in comp["platforms"]:
            raise PlanError(f"组件 {name} 不支持当前平台 {current}")
        conflicts = selected & set(comp["conflicts_with"])
        if conflicts:
            raise PlanError(f"组件 {name} 与 {', '.join(sorted(conflicts))} 冲突")
        for field in comp["fields"]:
            value = values.get(field["key"], field.get("default"))
            if field.get("required") and field["kind"] != "secret" and value in (None, ""):
                raise PlanError(f"缺少必填配置：{field.get('label') or field['key']}")
            if value not in (None, "") and field.get("pattern") and not re.fullmatch(
                    str(field["pattern"]), str(value)):
                raise PlanError(field.get("validation_message") or
                                f"配置格式无效：{field.get('label') or field['key']}")
    order = _toposort(selected, entries)
    actions = [{"component": "", "phase": "persist", "label": "保存基础配置"},
               {"component": "", "phase": "admin", "label": "创建本地恢复管理员"}]
    for name in order:
        for phase in ("deploy", "ready", "configure", "verify"):
            actions.append({"component": name, "phase": phase, "label": f"{name}: {phase}"})
    actions.append({"component": "", "phase": "finalize", "label": "完成初始化"})
    configuration_hash = hashlib.sha256(json.dumps(
        {"values": values, "secret_keys": sorted(k for k, present in (secret_presence or {}).items() if present)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    payload = {"schema_version": 1, "draft_revision": draft_revision, "profile": profile,
               "values": values,
               "components": [{"name": n, "reason": reasons[n],
                                "depends_on": entries[n]["component"]["depends_on"]} for n in order],
               "actions": actions, "catalog_revision": catalog.revision(entries),
               "configuration_hash": configuration_hash}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["plan_hash"] = hashlib.sha256(encoded.encode()).hexdigest()
    payload["environment_fingerprint"] = hashlib.sha256(
        json.dumps({"catalog": payload["catalog_revision"], "platform": current}, sort_keys=True).encode()).hexdigest()
    return payload
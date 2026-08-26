#!/usr/bin/env bash
# 手工导出 OpenProject 快照（ADR-0014：手工入口，无定时任务、不自动推送远端）
#
# 用法:
#   OPENPROJECT_API_KEY=<token> bash scripts/export-openproject.sh [输出目录]
#
# 输出: <输出目录>/<时间戳>/ 下 JSON 全量（projects/work_packages/relations/statuses）+ Markdown 摘要
# 默认输出目录: exports/openproject/（已入 .gitignore）
# 需要进 Git 审计时：把输出目录指到某个 git 仓库内，人工审查快照后自行 commit。
set -euo pipefail
cd "$(dirname "$0")/.."

OP="${OPENPROJECT_URL:-http://req.localhost}"
OUT="${1:-${OPENPROJECT_EXPORT_DIR:-exports/openproject}}"
: "${OPENPROJECT_API_KEY:?需要 OPENPROJECT_API_KEY（OpenProject → 我的账户 → 访问令牌；Basic 用户名固定 apikey）}"

python3 - "$OP" "$OUT" <<'PY'
import base64, json, os, sys, time, urllib.parse, urllib.request

base, out = sys.argv[1].rstrip("/"), sys.argv[2]
auth = base64.b64encode(("apikey:" + os.environ["OPENPROJECT_API_KEY"]).encode()).decode()
# 本机已知坑：代理会拦截 localhost/内网请求，显式禁用代理
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ts = time.strftime("%Y%m%d-%H%M%S")
d = os.path.join(out, ts)
os.makedirs(d, exist_ok=True)

def get(path, params=None):
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + auth})
    with opener.open(req) as r:
        return json.load(r)

def get_all(path):
    items, offset = [], 1
    while True:
        data = get(path, {"offset": offset, "pageSize": 200})
        items += data.get("_embedded", {}).get("elements", [])
        if len(items) >= data.get("total", 0):
            return items
        offset += 1

def dump(name, obj):
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def cell(wp, key):
    return (wp.get("_links", {}).get(key) or {}).get("title", "")

def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")

statuses = {s["id"]: s["name"] for s in get_all("/api/v3/statuses")}
projects = get_all("/api/v3/projects")
wps = get_all("/api/v3/work_packages")
relations = get_all("/api/v3/relations")

dump("statuses.json", statuses)
dump("projects.json", projects)
dump("work_packages.json", wps)
dump("relations.json", relations)

index = ["# OpenProject 导出快照", "",
         "- 时间: " + ts, "- 来源: " + base,
         "- 项目: %d · 工作包: %d · 关系: %d" % (len(projects), len(wps), len(relations)), ""]
for p in projects:
    rows = [w for w in wps if cell(w, "project") == p["name"]]
    fn = "project-%s.md" % p["id"]
    index.append("- [%s](%s)：%d 个工作包" % (p["name"], fn, len(rows)))
    with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
        f.write("# %s\n\n| ID | 主题 | 状态 | 指派 | 更新于 |\n|---|---|---|---|---|\n" % p["name"])
        for w in rows:
            f.write("| %s | %s | %s | %s | %s |\n" % (
                w["id"], esc(w["subject"]), esc(cell(w, "status")),
                esc(cell(w, "assignee")), w.get("updatedAt", "")))
with open(os.path.join(d, "INDEX.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(index) + "\n")

print("OK -> %s（%d 项目 / %d 工作包 / %d 关系）" % (d, len(projects), len(wps), len(relations)))
PY

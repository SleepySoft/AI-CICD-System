/* Chronicler supervisor 前端逻辑（Vue3 全局构建，无打包步骤） */
const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

const app = createApp({
  setup() {
    const user = ref(null);
    const loading = ref(false);
    const acting = ref(false);
    const loginError = ref("");
    const loginForm = ref({ username: "", password: "" });
    const authBackend = ref("local");
    const showLocalLogin = ref(false);
    const tab = ref("home");

    const projects = ref([]);
    const loadingProjects = ref(false);
    const runs = ref([]);
    const loadingRuns = ref(false);
    const runFilter = ref(null);
    const taskFilter = ref(null);
    const harnesses = ref([]);
    const defaultHarness = ref("");
    const defaultPublishPolicy = ref("direct");
    const showHarnessForm = ref(false);
    const editingHarnessName = ref("");
    const harnessForm = ref({ name: "", desc: "", command_template: "", prompt_mode: "file",
                              report_mode: "file", cwd: "repo", timeout_sec: 1800, env: [] });
    const components = ref({});
    const prompts = ref([]);
    const taskTypes = ref([]);
    const tools = ref([]);
    const loadingTools = ref(false);
    const showToolLog = ref(false);
    const toolLogName = ref("");
    const toolLogText = ref("");
    const showToolDetail = ref(false);
    const toolDetail = ref(null);
    const showDeploy = ref(false);
    const deployName = ref("");
    const deployState = ref("idle");
    const deployLines = ref([]);
    let deployTimer = null;
    const users = ref([]);
    const newUser = ref({ username: "", password: "", role: "user" });
    const showResetPw = ref(false);
    const resetPwUser = ref("");
    const resetPwForm = ref({ password: "", temporary: true });

    // ---- 秘密库（admin，ADR-0041~0044 一期）----
    const vaultItems = ref([]);
    const vaultAudit = ref([]);
    const loadingVault = ref(false);
    const vaultMaster = ref({ recipient: "", path: "" });
    const vaultMasterSecret = ref("");
    const showVaultMaster = ref(false);
    const showVaultText = ref(false);
    const vaultTextForm = ref({});
    const showVaultFile = ref(false);
    const vaultFileForm = ref({});
    let vaultFileData = null;  // 非响应式 File 对象
    const showVaultReveal = ref(false);
    const vaultRevealName = ref("");
    const vaultRevealValue = ref("");
    const showVaultEdit = ref(false);
    const vaultEditRow = ref(null);
    const vaultEditForm = ref({});

    const showNewProject = ref(false);
    const newProject = ref({ name: "", git_url: "", default_branch: "", ci_url: "", description: "", harness: "" });
    const showEdit = ref(false);
    const editProject = ref(null);
    const editForm = ref({ git_url: "", default_branch: "", ci_url: "", shadow_repo: "",
                           description: "", harness: "", showAdv: false, overridesText: "{}" });
    const showTrigger = ref(false);
    const triggerForm = ref({ project_id: null, task_type: "", extra_prompt: "" });

    const tasks = ref([]);
    const loadingTasks = ref(false);
    const showNewTask = ref(false);
    const newTaskForm = ref({ project_id: null, name: "", task_type: "", harness: "", cwd: "",
                              schedule_cron: "", change_policy: "always", change_probes: "[]", enabled: true });
    const showTaskEdit = ref(false);
    const taskEditRow = ref(null);
    const taskEditForm = ref({ name: "", harness: "", cwd: "", schedule_cron: "", enabled: true,
                               change_policy: "always", change_probes: "[]",
                               webhook: "", prompt_override: "" });
    const showPrompt = ref(false);
    const promptView = ref({ name: "", version: "", title: "", content: "", overridden: false,
                 disclosure: "full", content_hash: "", variables: [] });
    const showLog = ref(false);
    const logRunId = ref(null);
    const logText = ref("");
    const showReport = ref(false);
    const reportRunId = ref(null);
    const reportText = ref("");
    const showRunPrompt = ref(false);
    const runPromptId = ref(null);
    const runPromptText = ref("");
    let logTimer = null;
    let runPollTimer = null;

    const isAdmin = computed(() => user.value?.role === "admin");
    const componentList = computed(() =>
      Object.entries(components.value).map(([name, v]) => ({ name, ...v })));
    const taskPromptSource = computed(() => {
      if (!taskEditRow.value) return "";
      if (taskEditForm.value.prompt_override.trim()) return "当前生效：本任务自定义覆盖";
      const type = taskTypes.value.find(x => x.name === taskEditRow.value.task_type);
      const p = prompts.value.find(x => x.name === type?.prompt);
      if (!p) return "当前生效：全局模板";
      return `当前生效：${type.prompt} / ${type.mode} ${p.version}（${p.overridden ? "覆盖副本" : "内置"}）`;
    });
    const groupedTools = computed(() => {
      const g = {};
      for (const t of tools.value) (g[t.group || "其他"] ||= []).push(t);
      return g;
    });
    const groupedTaskDefs = computed(() => {
      const g = new Map();
      for (const t of tasks.value) {
        if (taskFilter.value && t.project_id !== taskFilter.value) continue;
        const key = t.project_id;
        if (!g.has(key)) g.set(key, { project_id: key, project_name: projectName(key), tasks: [] });
        g.get(key).tasks.push(t);
      }
      return [...g.values()];
    });

    async function api(path, opts = {}) {
      const resp = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
      if (resp.status === 401) { user.value = null; throw new Error("未登录"); }
      if (!resp.ok) {
        let msg = resp.statusText;
        try { msg = (await resp.json()).detail || msg; } catch (_) {}
        throw new Error(msg);
      }
      const ct = resp.headers.get("content-type") || "";
      return ct.includes("json") ? resp.json() : resp.text();
    }

    function fmtTime(ts) {
      if (!ts) return "-";
      return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
    }
    function open(url) { window.open(url, "_blank"); }
    function projectName(id) { return projects.value.find(p => p.id === id)?.name || `#${id}`; }
    function tasksOfProject(id) { return tasks.value.filter(t => t.project_id === id); }
    function runStatusText(s) {
      return { queued: "排队中", running: "运行中", success: "成功", failed: "失败", skipped: "已跳过" }[s] || s;
    }
    function runTagType(s) {
      return { queued: "info", running: "primary", success: "success", failed: "danger", skipped: "warning" }[s] || "info";
    }
    function changePolicyText(policy) {
      return { always: "始终运行", "repo-changed": "仓库变化", "inputs-changed": "任一输入变化" }[policy] || policy;
    }
    function shortRevision(revision) { return revision ? revision.slice(0, 8) : "无基线"; }
    function changeSummaryText(change) {
      const s = change?.change_summary || change || {};
      if (!s.state) return "历史 Run 无增量快照";
      const baseline = change?.baseline_run_id ? `Run #${change.baseline_run_id} · ` : "";
      const revisions = `${shortRevision(s.base_revision)} → ${shortRevision(s.head_revision)}`;
      if (s.state === "initial") return `首次执行 · ${shortRevision(s.head_revision)}`;
      if (s.state === "unchanged") return `${baseline}${revisions} · 无有效输入变化`;
      if (s.state === "changed") {
        const probes = s.changed_probes?.length ? ` · 输入:${s.changed_probes.join(",")}` : "";
        return `${baseline}${revisions} · ${s.commits || 0} commits · ${s.files || 0} files · +${s.insertions || 0}/-${s.deletions || 0}${probes}`;
      }
      if (s.state === "diverged") return `${baseline}${revisions} · 历史分叉`;
      return `${baseline}${revisions} · 增量未知${s.probe_errors?.length ? `：${s.probe_errors.join("；")}` : ""}`;
    }
    function changeConfirmText(change) {
      const summary = changeSummaryText(change);
      return change?.change_summary?.state === "unchanged"
        ? `未检测到有效输入增量。\n${summary}\n仍要启动 Agent 吗？`
        : `本次增量：${summary}\n确认启动 Agent？`;
    }
    function toolStatusText(t) {
      return { running: "运行中", stopped: "已停止", absent: "未部署", unknown: "未知" }[t.status] || t.status;
    }
    const toast = { ok: m => ElementPlus.ElMessage.success(m), err: e => ElementPlus.ElMessage.error(e.message) };

    function ssoLogin() { window.location.href = "/api/auth/oidc/login"; }

    async function login() {
      if (!loginForm.value.username || !loginForm.value.password) { loginError.value = "请输入用户名和密码"; return; }
      loading.value = true; loginError.value = "";
      try {
        user.value = await api("/api/auth/login", { method: "POST", body: JSON.stringify(loginForm.value) });
        loadAll();
      } catch (e) { loginError.value = e.message === "未登录" ? "用户名或密码错误" : e.message; }
      finally { loading.value = false; }
    }
    async function logout() {
      try { await api("/api/auth/logout", { method: "POST" }); } catch (_) {}
      user.value = null;
    }

    async function loadProjects() {
      loadingProjects.value = true;
      try {
        projects.value = (await api("/api/projects")).map(p => {
          // 兼容后端未重启时的旧格式（字符串 "hash subject"）
          if (p.last_commit && typeof p.last_commit === "string") {
            const m = p.last_commit.match(/^(\S+)\s?(.*)$/);
            p.last_commit = { hash: m?.[1] || p.last_commit, date: "", subject: m?.[2] || "" };
          }
          return p;
        });
      } catch (e) { toast.err(e); }
      finally { loadingProjects.value = false; }
    }
    function parseJson(text, field) {
      try { return JSON.parse(text || "{}"); }
      catch (_) { throw new Error(field + "不是合法 JSON"); }
    }
    async function createProject() {
      if (!newProject.value.name || !newProject.value.git_url) { ElementPlus.ElMessage.warning("名称与 Git 地址必填"); return; }
      acting.value = true;
      try {
        const overrides = parseJson(newProject.value.overrides || "{}", "覆盖项");
        if (newProject.value.harness) overrides.harness = newProject.value.harness;
        const body = { name: newProject.value.name, git_url: newProject.value.git_url,
                       default_branch: newProject.value.default_branch, ci_url: newProject.value.ci_url,
                       description: newProject.value.description, overrides };
        await api("/api/projects", { method: "POST", body: JSON.stringify(body) });
        toast.ok("工程已创建"); showNewProject.value = false;
        newProject.value = { name: "", git_url: "", ci_url: "", description: "", overrides: "{}" };
        loadProjects();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function syncProject(p) {
      try { await api(`/api/projects/${p.id}/sync`, { method: "POST" }); toast.ok(`已触发同步：${p.name}`); setTimeout(loadProjects, 2000); }
      catch (e) { toast.err(e); setTimeout(loadProjects, 1500); }
    }
    async function resetClone(p) {
      try {
        await ElementPlus.ElMessageBox.confirm(
          `将删除 ${p.name} 的工作空间克隆并重新拉取（档案与报告不受影响），继续？`,
          "重置克隆", { type: "warning", confirmButtonText: "重置", cancelButtonText: "取消" });
        await api(`/api/projects/${p.id}/reset-clone`, { method: "POST" });
        toast.ok("已重置并重新拉取"); setTimeout(loadProjects, 2000);
      } catch (e) {
        if (e !== "cancel" && e?.message) toast.err(e);
        setTimeout(loadProjects, 1500);
      }
    }
    function openEdit(p) {
      editProject.value = p;
      editForm.value = {
        git_url: p.git_url || "", default_branch: p.default_branch || "",
        ci_url: p.ci_url || "", shadow_repo: p.shadow_repo || "",
        description: p.description || "", harness: p.overrides?.harness || "",
        showAdv: false, overridesText: JSON.stringify(p.overrides ?? {}, null, 2),
      };
      showEdit.value = true;
    }
    async function saveEdit() {
      acting.value = true;
      try {
        const overrides = parseJson(editForm.value.overridesText, "覆盖项");
        if (editForm.value.harness) overrides.harness = editForm.value.harness;
        else delete overrides.harness;
        await api(`/api/projects/${editProject.value.id}`, {
          method: "PATCH",
          body: JSON.stringify({ git_url: editForm.value.git_url, default_branch: editForm.value.default_branch,
                                 ci_url: editForm.value.ci_url, shadow_repo: editForm.value.shadow_repo,
                                 description: editForm.value.description, overrides }),
        });
        toast.ok("工程设置已保存"); showEdit.value = false; loadProjects();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function removeProject(p) {
      try {
        await ElementPlus.ElMessageBox.confirm(
          `确认删除工程 ${p.name}？将同时删除本地克隆（runs/报告保留）。`, "删除工程", { type: "warning" });
        await api(`/api/projects/${p.id}`, { method: "DELETE" });
        toast.ok("已删除"); loadProjects();
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
    }

    async function loadTasks() {
      loadingTasks.value = true;
      try { tasks.value = await api("/api/tasks"); } catch (e) { toast.err(e); }
      finally { loadingTasks.value = false; }
    }
    function openNewTask() {
      newTaskForm.value = { project_id: projects.value[0]?.id || null, name: "",
                            task_type: taskTypes.value[0]?.name || "", harness: "", cwd: "",
                            schedule_cron: "", change_policy: "always", change_probes: "[]", enabled: true };
      showNewTask.value = true;
    }
    async function createTask() {
      const f = newTaskForm.value;
      if (!f.project_id || !f.name || !f.task_type) { ElementPlus.ElMessage.warning("工程、名称与任务类型必填"); return; }
      acting.value = true;
      try {
        const probes = parseJson(f.change_probes, "变更探针");
        if (!Array.isArray(probes)) throw new Error("变更探针必须是 JSON 数组");
        await api("/api/tasks", { method: "POST", body: JSON.stringify({
          project_id: f.project_id, name: f.name, task_type: f.task_type,
          harness: f.harness || "", cwd: f.cwd || "", schedule_cron: f.schedule_cron,
          change_policy: f.change_policy, change_probes: probes,
          enabled: f.enabled ? 1 : 0 }) });
        toast.ok("任务已创建"); showNewTask.value = false; loadTasks();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function toggleTaskEnabled(t, val) {
      try {
        await api(`/api/tasks/${t.id}`, { method: "PATCH", body: JSON.stringify({ enabled: val ? 1 : 0 }) });
        t.enabled = val ? 1 : 0;
        toast.ok(`已${val ? "启用" : "停用"}：${t.name}`);
      } catch (e) { toast.err(e); }  // 失败：switch 单向绑定，不落库即回弹
    }
    function openTaskEdit(t) {
      taskEditRow.value = t;
      taskEditForm.value = { name: t.name || "", harness: t.harness || "", cwd: t.cwd || "",
                             schedule_cron: t.schedule_cron || "",
                             change_policy: t.change_policy || "always",
                             change_probes: JSON.stringify(t.change_probes || [], null, 2),
                             enabled: !!t.enabled, webhook: t.webhook || "", prompt_override: t.prompt_override || "" };
      showTaskEdit.value = true;
    }
    async function saveTaskEdit() {
      acting.value = true;
      try {
        const probes = parseJson(taskEditForm.value.change_probes, "变更探针");
        if (!Array.isArray(probes)) throw new Error("变更探针必须是 JSON 数组");
        await api(`/api/tasks/${taskEditRow.value.id}`, { method: "PATCH", body: JSON.stringify({
          name: taskEditForm.value.name, harness: taskEditForm.value.harness || "",
          cwd: taskEditForm.value.cwd || "",
          schedule_cron: taskEditForm.value.schedule_cron,
          change_policy: taskEditForm.value.change_policy, change_probes: probes,
          enabled: taskEditForm.value.enabled ? 1 : 0, prompt_override: taskEditForm.value.prompt_override }) });
        toast.ok("任务已保存"); showTaskEdit.value = false; loadTasks();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function removeTask(t) {
      try {
        await ElementPlus.ElMessageBox.confirm(`确认删除任务「${t.name}」？执行记录（Run）保留。`, "删除任务", { type: "warning" });
        await api(`/api/tasks/${t.id}`, { method: "DELETE" });
        toast.ok("已删除"); loadTasks();
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
    }
    async function triggerTask(t) {
      let change;
      try { change = await api(`/api/tasks/${t.id}/changes`); }
      catch (e) { toast.err(e); return; }
      try {
        await ElementPlus.ElMessageBox.confirm(
          changeConfirmText(change),
          "触发任务", { type: "warning", confirmButtonText: "确认触发", cancelButtonText: "取消" });
      } catch (_) { return; }  // 取消
      acting.value = true;
      try {
        await api(`/api/tasks/${t.id}/trigger`, { method: "POST" });
        toast.ok(`已触发：${t.name}，开始执行`);
        await loadRuns();
        startRunPolling();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function openPrompt(p) {
      promptView.value = { ...p, content: "加载中…" };
      showPrompt.value = true;
      try {
        promptView.value = await api(`/api/config/prompts/${encodeURIComponent(p.name)}/content`);
        promptView.value.content ||= "";
      }
      catch (e) { toast.err(e); showPrompt.value = false; }
    }
    async function savePrompt() {
      acting.value = true;
      try {
        const r = await api(`/api/config/prompts/${encodeURIComponent(promptView.value.name)}`,
                            { method: "PUT", body: JSON.stringify({
                              version: promptView.value.version, content: promptView.value.content }) });
        toast.ok(`已保存为覆盖副本${r.version ? `（${r.version}）` : ""}`);
        promptView.value.overridden = true;
        promptView.value.disclosure = "full";
        promptView.value.content_hash = r.content_hash || promptView.value.content_hash;
        loadConfig();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function resetPrompt() {
      try {
        await ElementPlus.ElMessageBox.confirm(
          `确认删除「${promptView.value.name}」的覆盖副本并回落到内置模板？`, "恢复内置", { type: "warning" });
        await api(`/api/config/prompts/${encodeURIComponent(promptView.value.name)}/override`, { method: "DELETE" });
        toast.ok("已恢复内置模板");
        await openPrompt(promptView.value);
        loadConfig();
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
    }

    async function loadRuns() {
      loadingRuns.value = true;
      try {
        const q = runFilter.value ? `?project_id=${runFilter.value}` : "";
        runs.value = await api("/api/runs" + q);
        // 有排队/运行中任务则持续轮询刷新（进度反应），全部结束即停
        if (runs.value.some(r => r.status === "running" || r.status === "queued")) startRunPolling();
        else stopRunPolling();
      } catch (e) { toast.err(e); }
      finally { loadingRuns.value = false; }
    }
    function runRowClass({ row }) {
      return (row.status === "running" || row.status === "queued") ? "run-row-active" : "";
    }
    function startRunPolling() {
      if (runPollTimer) return;
      runPollTimer = setInterval(loadRuns, 3000);
    }
    function stopRunPolling() {
      if (runPollTimer) { clearInterval(runPollTimer); runPollTimer = null; }
    }
    function openTrigger() {
      triggerForm.value = { project_id: runFilter.value || projects.value[0]?.id || null, task_type: taskTypes.value[0]?.name || "", extra_prompt: "" };
      showTrigger.value = true;
    }
    async function triggerRun() {
      if (!triggerForm.value.project_id || !triggerForm.value.task_type) { ElementPlus.ElMessage.warning("请选择工程与任务类型"); return; }
      try {
        const query = new URLSearchParams({ project_id: triggerForm.value.project_id,
                                            task_type: triggerForm.value.task_type });
        const change = await api(`/api/runs/change-preview?${query}`);
        await ElementPlus.ElMessageBox.confirm(changeConfirmText(change), "触发任务",
          { type: change.change_summary?.state === "unchanged" ? "warning" : "info",
            confirmButtonText: "确认触发", cancelButtonText: "取消" });
      } catch (e) {
        if (e === "cancel" || e === "close") return;
        toast.err(e); return;
      }
      acting.value = true;
      try {
        await api("/api/runs/trigger", { method: "POST", body: JSON.stringify(triggerForm.value) });
        toast.ok("任务已触发，开始执行"); showTrigger.value = false;
        await loadRuns();
        startRunPolling();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function fetchLog() {
      if (!logRunId.value) return;
      try { logText.value = await api(`/api/runs/${logRunId.value}/log`); }
      catch (e) { logText.value = `（获取失败: ${e.message}）`; stopLogPoll(); }
    }
    function stopLogPoll() { if (logTimer) { clearInterval(logTimer); logTimer = null; } }
    async function openLog(run) {
      logRunId.value = run.id; logText.value = ""; showLog.value = true;
      await fetchLog();
      stopLogPoll();
      if (run.status === "running" || run.status === "queued") logTimer = setInterval(fetchLog, 2000);
    }
    async function openReport(run) {
      reportRunId.value = run.id; reportText.value = "加载中…"; showReport.value = true;
      try { reportText.value = (await api(`/api/runs/${run.id}/report`)) || "（空报告）"; }
      catch (e) { reportText.value = `（${e.message}）`; }
    }
    async function openRunPrompt(run) {
      runPromptId.value = run.id; runPromptText.value = "加载中…"; showRunPrompt.value = true;
      try { runPromptText.value = (await api(`/api/runs/${run.id}/prompt`)) || "（暂无记录）"; }
      catch (e) { runPromptText.value = `（${e.message}）`; }
    }

    async function loadConfig() {
      try {
        const [loadedHarnesses, loadedComponents, loadedPrompts, loadedTaskTypes, settings] = await Promise.all([
          api("/api/config/harnesses"), api("/api/config/components"),
          api("/api/config/prompts"), api("/api/config/task-types"), api("/api/config/settings"),
        ]);
        harnesses.value = loadedHarnesses;
        components.value = loadedComponents;
        prompts.value = loadedPrompts;
        taskTypes.value = loadedTaskTypes;
        defaultHarness.value = settings.default_harness || "";
        defaultPublishPolicy.value = settings.default_publish_policy || "direct";
      } catch (e) { toast.err(e); }
    }
    async function saveDefaultHarness() {
      if (!defaultHarness.value) { toast.err(new Error("请选择默认 harness")); return; }
      acting.value = true;
      try {
        await api("/api/config/settings", { method: "PUT", body: JSON.stringify({
          default_harness: defaultHarness.value,
          default_publish_policy: defaultPublishPolicy.value,
        }) });
        toast.ok("全局默认配置已保存");
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    function openHarnessForm(h) {
      editingHarnessName.value = h?.name || "";
      harnessForm.value = h ? {
        name: h.name, desc: h.desc || "", command_template: h.command_template,
        prompt_mode: h.stdin_prompt ? "stdin" : "file",
        report_mode: h.report_mode || "file", cwd: h.cwd || "repo",
        timeout_sec: h.timeout_sec || 1800,
        env: (h.env_keys || []).map(k => ({ key: k, value: "" })),  // 密钥不回显；空值=保持原值
      } : { name: "", desc: "", command_template: "", prompt_mode: "file",
             report_mode: "file", cwd: "repo", timeout_sec: 1800, env: [] };
      showHarnessForm.value = true;
    }
    function buildEnvObject(rows) {
      const obj = {};
      for (const r of rows || []) {
        const k = (r.key || "").trim();
        if (k) obj[k] = (r.value || "").trim();
      }
      return obj;
    }
    async function saveHarness() {
      const f = harnessForm.value;
      if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(f.name || "")) { toast.err(new Error("name 需为英数/连字符/下划线且非空")); return; }
      if (!f.command_template || !f.command_template.trim()) { toast.err(new Error("command_template 不能为空")); return; }
      acting.value = true;
      try {
        await api("/api/config/harnesses", { method: "POST", body: JSON.stringify({
          name: f.name, desc: f.desc, command_template: f.command_template.trim(),
          session: "once", stdin_prompt: f.prompt_mode === "stdin",
          report_mode: f.report_mode, cwd: f.cwd, timeout_sec: f.timeout_sec,
          env: buildEnvObject(f.env),
        })});
        toast.ok("Harness 已保存");
        showHarnessForm.value = false;
        loadConfig();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function removeHarness(h) {
      try {
        await ElementPlus.ElMessageBox.confirm(
          `确认删除 harness ${h.name}？内置条目删除后会写入 DATA 覆盖文件，需要时可从 git 恢复。`,
          "删除 Harness", { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" });
        await api(`/api/config/harnesses/${encodeURIComponent(h.name)}`, { method: "DELETE" });
        toast.ok("已删除");
        if (defaultHarness.value === h.name) defaultHarness.value = "";
        loadConfig();
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
    }
    async function loadTools() {
      loadingTools.value = true;
      try { tools.value = await api("/api/tools"); } catch (e) { toast.err(e); }
      finally { loadingTools.value = false; }
    }
    async function ctlTool(t, action) {
      if (action === "deploy") { openDeploy(t); return; }
      if (action !== "start") {
        const msg = t.critical
          ? `${t.desc || t.name} 是关键组件，${action === "stop" ? "停止" : "重启"}它可能影响统一认证与系统入口，确认继续？`
          : `${t.desc || t.name} 将被${action === "stop" ? "停止" : "重启"}，可能短暂影响依赖它的功能，确认继续？`;
        try {
          await ElementPlus.ElMessageBox.confirm(
            msg, "组件操作", { type: "warning", confirmButtonText: "确认执行", cancelButtonText: "取消" });
        } catch (_) { return; }
      }
      if (action === "deploy") toast.ok(`${t.name} 部署中（首次需拉取镜像，可能数分钟）…`);
      try {
        await api(`/api/tools/${t.name}/${action}`, { method: "POST" });
        toast.ok(`${t.name} ${action} 已执行`); setTimeout(loadTools, 1500);
      } catch (e) { toast.err(e); }
    }
    async function toggleAutostart(t, val) {
      if (!val) {
        const msg = t.critical
          ? `${t.desc || t.name} 是关键组件，关闭自启后 supervisor 重启时将不再自动拉起它，确认关闭？`
          : `${t.desc || t.name} 关闭自启后，supervisor 重启时将不再自动拉起它，确认关闭？`;
        try {
          await ElementPlus.ElMessageBox.confirm(
            msg,
            "关闭自启", { type: "warning", confirmButtonText: "确认关闭", cancelButtonText: "取消" });
        } catch (_) { return; }  // 取消：switch 用 model-value 单向绑定，不落库即回弹
      }
      try {
        await api(`/api/tools/${t.name}/autostart`, { method: "POST", body: JSON.stringify({ enabled: val }) });
        t.autostart = val;
        toast.ok(`${t.name} 自启已${val ? "开启" : "关闭"}`);
      } catch (e) { toast.err(e); }
    }
    async function openToolLogs(t) {
      showToolLog.value = true; toolLogName.value = t.name; toolLogText.value = "加载中...";
      await refreshToolLogs();
    }
    async function refreshToolLogs() {
      try { toolLogText.value = await api(`/api/tools/${toolLogName.value}/logs?tail=300`); }
      catch (e) { toolLogText.value = `（获取失败: ${e.message}）`; }
    }
    async function openToolDetail(t) {
      showToolDetail.value = true;
      try { toolDetail.value = await api(`/api/tools/${t.name}/detail`); }
      catch (e) { toast.err(e); showToolDetail.value = false; }
    }
    async function openDeploy(t) {
      showDeploy.value = true; deployName.value = t.name;
      deployState.value = "running"; deployLines.value = [];
      try { await api(`/api/tools/${t.name}/deploy`, { method: "POST" }); }
      catch (e) { toast.err(e); }
      pollDeploy();
    }
    async function pollDeploy() {
      if (!showDeploy.value) return;
      try {
        const r = await api(`/api/tools/${deployName.value}/deploy-log`);
        deployState.value = r.state; deployLines.value = r.lines;
        if (r.state === "running") deployTimer = setTimeout(pollDeploy, 1500);
        else { loadTools(); if (r.state === "done") toast.ok(`${deployName.value} 部署完成`); }
      } catch (e) { /* 轮询失败下轮再试 */ deployTimer = setTimeout(pollDeploy, 3000); }
    }
    function closeDeploy() { showDeploy.value = false; if (deployTimer) clearTimeout(deployTimer); loadTools(); }
    function fmtUptime(sec) {
      if (sec == null) return "-";
      const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60);
      return (d ? d + "天" : "") + (h ? h + "小时" : "") + m + "分钟";
    }
    function fmtPorts(ports) {
      const out = [];
      for (const [k, v] of Object.entries(ports || {})) if (v) out.push(`${v.map(x => x.HostPort).join(",")}→${k}`);
      return out.join("  ") || "（无映射）";
    }
    async function loadUsers() {
      try { users.value = await api("/api/users"); } catch (e) { toast.err(e); }
    }
    async function createUser() {
      if (!newUser.value.username || !newUser.value.password) { ElementPlus.ElMessage.warning("用户名与密码必填"); return; }
      acting.value = true;
      try {
        await api("/api/users", { method: "POST", body: JSON.stringify(newUser.value) });
        toast.ok("用户已创建"); newUser.value = { username: "", password: "", role: "user" }; loadUsers();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    function openResetPw(u) {
      resetPwUser.value = u.username;
      resetPwForm.value = { password: "", temporary: true };
      showResetPw.value = true;
    }
    async function doResetPw() {
      if (resetPwForm.value.password.length < 6) { toast.err(new Error("密码至少 6 位")); return; }
      try {
        await ElementPlus.ElMessageBox.confirm(
          `确认重置用户 ${resetPwUser.value} 的密码？重置后原密码立即失效。`,
          "重置密码", { type: "warning", confirmButtonText: "确认重置", cancelButtonText: "取消" });
      } catch (_) { return; }
      acting.value = true;
      try {
        await api(`/api/users/${resetPwUser.value}/reset-password`,
                  { method: "POST", body: JSON.stringify(resetPwForm.value) });
        toast.ok(`已重置 ${resetPwUser.value} 的密码`);
        showResetPw.value = false;
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function removeUser(u) {
      try {
        await ElementPlus.ElMessageBox.confirm(`确认删除用户 ${u.username}？`, "删除用户", { type: "warning" });
        await api(`/api/users/${u.id}`, { method: "DELETE" });
        toast.ok("已删除"); loadUsers();
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
    }

    // ---- 秘密库 ----
    function fmtSize(n) {
      if (n == null) return "-";
      if (n < 1024) return n + "B";
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + "KB";
      return (n / 1024 / 1024).toFixed(1) + "MB";
    }
    async function apiRaw(path, opts = {}) {  // 非 JSON 响应（文本/文件下载）的 fetch 封装
      const resp = await fetch(path, opts);
      if (resp.status === 401) { user.value = null; throw new Error("未登录"); }
      if (!resp.ok) {
        let msg = resp.statusText;
        try { msg = (await resp.json()).detail || msg; } catch (_) {}
        throw new Error(msg);
      }
      return resp;
    }
    function saveBlob(blob, filename) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    }
    function downloadFilename(resp, fallback) {
      const cd = resp.headers.get("content-disposition") || "";
      const m = cd.match(/filename="?([^";]+)/);
      return m ? m[1] : fallback;
    }
    async function loadVault() {
      loadingVault.value = true;
      try {
        const [items, master, auditRows] = await Promise.all([
          api("/api/vault"), api("/api/vault/master"), api("/api/vault/audit"),
        ]);
        vaultItems.value = items;
        vaultMaster.value = master;
        vaultAudit.value = auditRows;
      } catch (e) { toast.err(e); }
      finally { loadingVault.value = false; }
    }
    function openVaultText() {
      vaultTextForm.value = { name: "", scope: "infra", secret_type: "password",
                              rotation_risk: "coordinated", summary: "", owner: "",
                              expires_at: null, value: "" };
      showVaultText.value = true;
    }
    async function createVaultText() {
      const f = vaultTextForm.value;
      if (!f.name || !f.value) { ElementPlus.ElMessage.warning("名称与值必填"); return; }
      acting.value = true;
      try {
        await api("/api/vault/text", { method: "POST", body: JSON.stringify({
          name: f.name, scope: f.scope || "infra", secret_type: f.secret_type,
          rotation_risk: f.rotation_risk, summary: f.summary, owner: f.owner,
          expires_at: f.expires_at ? Number(f.expires_at) : null, value: f.value }) });
        toast.ok("已加密保存"); showVaultText.value = false; loadVault();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    function openVaultFile() {
      vaultFileForm.value = { name: "", scope: "signing", secret_type: "access-key",
                              rotation_risk: "critical", summary: "", owner: "", expires_at: null };
      vaultFileData = null;
      showVaultFile.value = true;
    }
    function onVaultFileChange(uploadFile) { vaultFileData = uploadFile.raw; }
    function onVaultFileRemove() { vaultFileData = null; }
    async function createVaultFile() {
      if (!vaultFileData) { ElementPlus.ElMessage.warning("请选择文件"); return; }
      acting.value = true;
      try {
        const fd = new FormData();
        fd.append("file", vaultFileData);
        for (const [k, v] of Object.entries(vaultFileForm.value)) {
          if (v !== null && v !== "") fd.append(k, v);
        }
        await apiRaw("/api/vault/file", { method: "POST", body: fd });
        toast.ok("已加密保存"); showVaultFile.value = false; loadVault();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function revealVault(row) {
      try {
        const resp = await apiRaw(`/api/vault/${row.id}/reveal`, { method: "POST" });
        vaultRevealValue.value = await resp.text();
        vaultRevealName.value = `${row.scope}/${row.name}`;
        showVaultReveal.value = true;
        loadVaultAuditOnly();
      } catch (e) { toast.err(e); }
    }
    async function downloadVault(row) {
      try {
        const resp = await apiRaw(`/api/vault/${row.id}/download`);
        saveBlob(await resp.blob(), downloadFilename(resp, row.filename || row.name));
        toast.ok("已下载（已写审计）"); loadVaultAuditOnly();
      } catch (e) { toast.err(e); }
    }
    function openVaultEdit(row) {
      vaultEditRow.value = row;
      vaultEditForm.value = { summary: row.summary || "", owner: row.owner || "",
                              secret_type: row.secret_type, rotation_risk: row.rotation_risk,
                              expires_at: row.expires_at ? String(row.expires_at) : null, value: "" };
      showVaultEdit.value = true;
    }
    async function saveVaultEdit() {
      const f = vaultEditForm.value, row = vaultEditRow.value;
      acting.value = true;
      try {
        await api(`/api/vault/${row.id}`, { method: "PATCH", body: JSON.stringify({
          summary: f.summary, owner: f.owner, secret_type: f.secret_type,
          rotation_risk: f.rotation_risk,
          expires_at: f.expires_at ? Number(f.expires_at) : null }) });
        if (f.value && f.value.trim()) {
          if (row.rotation_risk === "critical") {
            await ElementPlus.ElMessageBox.confirm(
              "该秘密标记为高危轮换：旧值加密的数据/会话将不可恢复，确认轮换？",
              "高危轮换", { type: "error", confirmButtonText: "确认轮换", cancelButtonText: "取消" });
          }
          await api(`/api/vault/${row.id}/value`, { method: "POST", body: JSON.stringify({ value: f.value }) });
          toast.ok("元数据已保存，值已轮换");
        } else {
          toast.ok("已保存");
        }
        showVaultEdit.value = false; loadVault();
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
      finally { acting.value = false; }
    }
    async function removeVault(row) {
      try {
        await ElementPlus.ElMessageBox.confirm(
          `确认删除秘密 ${row.scope}/${row.name}？删除后仅存于历史导出包中。`,
          "删除秘密", { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" });
        await api(`/api/vault/${row.id}`, { method: "DELETE" });
        toast.ok("已删除"); loadVault();
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
    }
    async function exportVault() {
      try {
        const resp = await apiRaw("/api/vault/export");
        saveBlob(await resp.blob(), downloadFilename(resp, "vault-export.tar"));
        toast.ok("导出包已下载：manifest.json 明文可浏览，payload.age 需主密钥解密（scripts/vault-inspect.py）");
        loadVaultAuditOnly();
      } catch (e) { toast.err(e); }
    }
    async function revealMaster() {
      try {
        await ElementPlus.ElMessageBox.confirm(
          "主密钥可解开全部秘密。请立即转存密码管理器并做离线备份。本次查看将写审计。",
          "显示主密钥", { type: "warning", confirmButtonText: "显示", cancelButtonText: "取消" });
        const r = await api("/api/vault/master/reveal", { method: "POST" });
        vaultMasterSecret.value = r.secret;
        showVaultMaster.value = true;
        loadVaultAuditOnly();
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
    }
    async function loadVaultAuditOnly() {
      try { vaultAudit.value = await api("/api/vault/audit"); } catch (_) {}
    }

    function loadAll() {
      loadProjects(); loadRuns(); loadTasks(); loadConfig(); loadTools();
      if (isAdmin.value) loadUsers();
    }
    function onTabChange(name) {
      if (location.hash.slice(1) !== name) history.replaceState(null, "", "#" + name);
      if (name === "home") loadTools();
      else if (name === "projects") { loadProjects(); loadTasks(); }
      else if (name === "runs") { loadTasks(); loadRuns(); }
      else if (name === "config") loadConfig();
      else if (name === "users") loadUsers();
      else if (name === "vault") loadVault();
    }

    onMounted(async () => {
      const h = location.hash.slice(1);
      if (h) tab.value = h;
      window.addEventListener("hashchange", () => { if (location.hash.slice(1) !== tab.value) tab.value = location.hash.slice(1) || "home"; });
      try { authBackend.value = (await api("/api/auth/method")).backend; } catch (_) {}
      try { user.value = await api("/api/auth/me"); } catch (_) { user.value = null; }
      if (user.value) loadAll();
    });
    onUnmounted(() => { stopLogPoll(); stopRunPolling(); });

    return {
      user, loading, acting, loginError, loginForm, authBackend, ssoLogin, showLocalLogin, tab, isAdmin,
      projects, loadingProjects, runs, loadingRuns, runFilter,
      harnesses, components, componentList, prompts, taskTypes,
      defaultHarness, defaultPublishPolicy, showHarnessForm, editingHarnessName, harnessForm,
      tools, loadingTools, groupedTools, users, newUser,
      showToolLog, toolLogName, toolLogText, showToolDetail, toolDetail,
      showDeploy, deployName, deployState, deployLines, openDeploy, closeDeploy,
      toggleAutostart, openToolLogs, refreshToolLogs, openToolDetail, fmtUptime, fmtPorts,
      showNewProject, newProject, showEdit, editProject, editForm,
      showTrigger, triggerForm, showLog, logRunId, logText, showReport, reportRunId, reportText,
      showRunPrompt, runPromptId, runPromptText,
      tasks, loadingTasks, taskFilter, groupedTaskDefs, tasksOfProject,
      showNewTask, newTaskForm, showTaskEdit, taskEditRow, taskEditForm,
      showPrompt, promptView, taskPromptSource,
      fmtTime, open, projectName, runStatusText, runTagType, toolStatusText,
      changePolicyText, changeSummaryText,
      login, logout, onTabChange,
      loadProjects, createProject, syncProject, resetClone, openEdit, saveEdit, removeProject,
      loadRuns, openTrigger, triggerRun, openLog, openReport, openRunPrompt, stopLogPoll,
      runRowClass,
      loadTasks, openNewTask, createTask, toggleTaskEnabled, openTaskEdit, saveTaskEdit, removeTask, triggerTask,
      openPrompt, savePrompt, resetPrompt,
      loadTools, ctlTool, createUser, removeUser, openResetPw, doResetPw, showResetPw, resetPwUser, resetPwForm,
      saveDefaultHarness, openHarnessForm, saveHarness, removeHarness,
      vaultItems, vaultAudit, loadingVault, vaultMaster, vaultMasterSecret, showVaultMaster,
      showVaultText, vaultTextForm, showVaultFile, vaultFileForm,
      showVaultReveal, vaultRevealName, vaultRevealValue, showVaultEdit, vaultEditRow, vaultEditForm,
      fmtSize, loadVault, openVaultText, createVaultText, openVaultFile, onVaultFileChange,
      onVaultFileRemove, createVaultFile, revealVault, downloadVault, openVaultEdit,
      saveVaultEdit, removeVault, exportVault, revealMaster,
    };
  },
});

for (const [name, component] of Object.entries(ElementPlusIconsVue)) app.component(name, component);
app.use(ElementPlus).mount("#app");

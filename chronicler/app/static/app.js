/* Chronicler supervisor 前端逻辑（Vue3 全局构建，无打包步骤） */
const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

createApp({
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
    const harnesses = ref([]);
    const components = ref({});
    const prompts = ref([]);
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
    const newTaskForm = ref({ project_id: null, name: "", task_type: "", schedule_cron: "", enabled: true });
    const showTaskEdit = ref(false);
    const taskEditRow = ref(null);
    const taskEditForm = ref({ name: "", schedule_cron: "", enabled: true, webhook: "", prompt_override: "" });
    const showPrompt = ref(false);
    const promptView = ref({ task_type: "", version: "", content: "", overridden: false });
    const showLog = ref(false);
    const logRunId = ref(null);
    const logText = ref("");
    const showReport = ref(false);
    const reportRunId = ref(null);
    const reportText = ref("");
    let logTimer = null;

    const isAdmin = computed(() => user.value?.role === "admin");
    const componentList = computed(() =>
      Object.entries(components.value).map(([name, v]) => ({ name, ...v })));
    const taskPromptSource = computed(() => {
      if (!taskEditRow.value) return "";
      if (taskEditForm.value.prompt_override.trim()) return "当前生效：本任务自定义覆盖";
      const p = prompts.value.find(x => x.task_type === taskEditRow.value.task_type);
      if (!p) return "当前生效：全局模板";
      return `当前生效：全局模板 ${p.version}（${p.overridden ? "覆盖副本" : "内置"}）`;
    });
    const groupedTools = computed(() => {
      const g = {};
      for (const t of tools.value) (g[t.group || "其他"] ||= []).push(t);
      return g;
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
    function runStatusText(s) {
      return { queued: "排队中", running: "运行中", success: "成功", failed: "失败" }[s] || s;
    }
    function runTagType(s) {
      return { queued: "info", running: "primary", success: "success", failed: "danger" }[s] || "info";
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
      try { projects.value = await api("/api/projects"); } catch (e) { toast.err(e); }
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
      catch (e) { toast.err(e); }
    }
    async function resetClone(p) {
      try {
        await ElementPlus.ElMessageBox.confirm(
          `将删除 ${p.name} 的工作空间克隆并重新拉取（档案与报告不受影响），继续？`,
          "重置克隆", { type: "warning", confirmButtonText: "重置", cancelButtonText: "取消" });
        await api(`/api/projects/${p.id}/reset-clone`, { method: "POST" });
        toast.ok("已重置并重新拉取"); setTimeout(loadProjects, 2000);
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
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
                            task_type: prompts.value[0]?.task_type || "", schedule_cron: "", enabled: true };
      showNewTask.value = true;
    }
    async function createTask() {
      const f = newTaskForm.value;
      if (!f.project_id || !f.name || !f.task_type) { ElementPlus.ElMessage.warning("工程、名称与任务类型必填"); return; }
      acting.value = true;
      try {
        await api("/api/tasks", { method: "POST", body: JSON.stringify({
          project_id: f.project_id, name: f.name, task_type: f.task_type,
          schedule_cron: f.schedule_cron, enabled: f.enabled ? 1 : 0 }) });
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
      taskEditForm.value = { name: t.name || "", schedule_cron: t.schedule_cron || "",
                             enabled: !!t.enabled, webhook: t.webhook || "", prompt_override: t.prompt_override || "" };
      showTaskEdit.value = true;
    }
    async function saveTaskEdit() {
      acting.value = true;
      try {
        await api(`/api/tasks/${taskEditRow.value.id}`, { method: "PATCH", body: JSON.stringify({
          name: taskEditForm.value.name, schedule_cron: taskEditForm.value.schedule_cron,
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
      try {
        await api(`/api/tasks/${t.id}/trigger`, { method: "POST" });
        toast.ok(`已触发：${t.name}`); setTimeout(loadRuns, 800);
      } catch (e) { toast.err(e); }
    }
    async function openPrompt(p) {
      promptView.value = { task_type: p.task_type, version: p.version, content: "加载中…", overridden: p.overridden };
      showPrompt.value = true;
      try { promptView.value = await api(`/api/config/prompts/${encodeURIComponent(p.task_type)}/content`); }
      catch (e) { toast.err(e); showPrompt.value = false; }
    }
    async function savePrompt() {
      acting.value = true;
      try {
        const r = await api(`/api/config/prompts/${encodeURIComponent(promptView.value.task_type)}`,
                            { method: "PUT", body: JSON.stringify({ content: promptView.value.content }) });
        toast.ok(`已保存为覆盖副本${r.version ? `（${r.version}）` : ""}`);
        promptView.value.overridden = true;
        loadConfig();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
    }
    async function resetPrompt() {
      try {
        await ElementPlus.ElMessageBox.confirm(
          `确认删除「${promptView.value.task_type}」的覆盖副本并回落到内置模板？`, "恢复内置", { type: "warning" });
        await api(`/api/config/prompts/${encodeURIComponent(promptView.value.task_type)}/override`, { method: "DELETE" });
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
      } catch (e) { toast.err(e); }
      finally { loadingRuns.value = false; }
    }
    function openTrigger() {
      triggerForm.value = { project_id: runFilter.value || projects.value[0]?.id || null, task_type: prompts.value[0]?.task_type || "", extra_prompt: "" };
      showTrigger.value = true;
    }
    async function triggerRun() {
      if (!triggerForm.value.project_id || !triggerForm.value.task_type) { ElementPlus.ElMessage.warning("请选择工程与任务类型"); return; }
      acting.value = true;
      try {
        await api("/api/runs/trigger", { method: "POST", body: JSON.stringify(triggerForm.value) });
        toast.ok("任务已触发"); showTrigger.value = false; setTimeout(loadRuns, 800);
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

    async function loadConfig() {
      try {
        [harnesses.value, components.value, prompts.value] = await Promise.all([
          api("/api/config/harnesses"), api("/api/config/components"), api("/api/config/prompts"),
        ]);
      } catch (e) { toast.err(e); }
    }
    async function loadTools() {
      loadingTools.value = true;
      try { tools.value = await api("/api/tools"); } catch (e) { toast.err(e); }
      finally { loadingTools.value = false; }
    }
    async function ctlTool(t, action) {
      if (action === "deploy") { openDeploy(t); return; }
      if (t.critical && action !== "start") {
        try {
          await ElementPlus.ElMessageBox.confirm(
            `${t.desc || t.name} 是关键组件，${action === "stop" ? "停止" : "重启"}它可能影响统一认证与系统入口，确认继续？`,
            "关键组件操作", { type: "warning", confirmButtonText: "确认执行", cancelButtonText: "取消" });
        } catch (_) { return; }
      }
      if (action === "deploy") toast.ok(`${t.name} 部署中（首次需拉取镜像，可能数分钟）…`);
      try {
        await api(`/api/tools/${t.name}/${action}`, { method: "POST" });
        toast.ok(`${t.name} ${action} 已执行`); setTimeout(loadTools, 1500);
      } catch (e) { toast.err(e); }
    }
    async function toggleAutostart(t, val) {
      if (t.critical && !val) {
        try {
          await ElementPlus.ElMessageBox.confirm(
            `${t.desc || t.name} 是关键组件，关闭自启后 supervisor 重启时将不再自动拉起它，确认关闭？`,
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

    function loadAll() {
      loadProjects(); loadRuns(); loadTasks(); loadConfig(); loadTools();
      if (isAdmin.value) loadUsers();
    }
    function onTabChange(name) {
      if (name === "home") loadTools();
      else if (name === "projects") loadProjects();
      else if (name === "runs") { loadTasks(); loadRuns(); }
      else if (name === "config") loadConfig();
      else if (name === "users") loadUsers();
    }

    onMounted(async () => {
      try { authBackend.value = (await api("/api/auth/method")).backend; } catch (_) {}
      try { user.value = await api("/api/auth/me"); } catch (_) { user.value = null; }
      if (user.value) loadAll();
    });
    onUnmounted(stopLogPoll);

    return {
      user, loading, acting, loginError, loginForm, authBackend, ssoLogin, showLocalLogin, tab, isAdmin,
      projects, loadingProjects, runs, loadingRuns, runFilter,
      harnesses, components, componentList, prompts,
      tools, loadingTools, groupedTools, users, newUser,
      showToolLog, toolLogName, toolLogText, showToolDetail, toolDetail,
      showDeploy, deployName, deployState, deployLines, openDeploy, closeDeploy,
      toggleAutostart, openToolLogs, refreshToolLogs, openToolDetail, fmtUptime, fmtPorts,
      showNewProject, newProject, showEdit, editProject, editForm,
      showTrigger, triggerForm, showLog, logRunId, logText, showReport, reportRunId, reportText,
      tasks, loadingTasks, showNewTask, newTaskForm, showTaskEdit, taskEditRow, taskEditForm,
      showPrompt, promptView, taskPromptSource,
      fmtTime, open, projectName, runStatusText, runTagType, toolStatusText,
      login, logout, onTabChange,
      loadProjects, createProject, syncProject, resetClone, openEdit, saveEdit, removeProject,
      loadRuns, openTrigger, triggerRun, openLog, openReport, stopLogPoll,
      loadTasks, openNewTask, createTask, toggleTaskEnabled, openTaskEdit, saveTaskEdit, removeTask, triggerTask,
      openPrompt, savePrompt, resetPrompt,
      loadTools, ctlTool, createUser, removeUser, openResetPw, doResetPw, showResetPw, resetPwUser, resetPwForm,
    };
  },
}).use(ElementPlus).mount("#app");

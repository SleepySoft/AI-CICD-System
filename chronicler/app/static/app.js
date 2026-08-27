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
    const users = ref([]);
    const newUser = ref({ username: "", password: "", role: "user" });

    const showNewProject = ref(false);
    const newProject = ref({ name: "", git_url: "", ci_url: "", description: "", overrides: "{}" });
    const showOverrides = ref(false);
    const editProject = ref(null);
    const overridesText = ref("");
    const showTrigger = ref(false);
    const triggerForm = ref({ project_id: null, task_type: "", extra_prompt: "" });
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
        const body = { ...newProject.value, overrides: parseJson(newProject.value.overrides, "覆盖项") };
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
    function openOverrides(p) {
      editProject.value = p;
      overridesText.value = JSON.stringify(p.overrides ?? {}, null, 2);
      showOverrides.value = true;
    }
    async function saveOverrides() {
      acting.value = true;
      try {
        await api(`/api/projects/${editProject.value.id}`, {
          method: "PATCH", body: JSON.stringify({ overrides: parseJson(overridesText.value, "覆盖项") }),
        });
        toast.ok("覆盖项已保存"); showOverrides.value = false; loadProjects();
      } catch (e) { toast.err(e); }
      finally { acting.value = false; }
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
      try {
        await api(`/api/tools/${t.name}/${action}`, { method: "POST" });
        toast.ok(`${t.name} ${action} 已执行`); setTimeout(loadTools, 1500);
      } catch (e) { toast.err(e); }
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
    async function removeUser(u) {
      try {
        await ElementPlus.ElMessageBox.confirm(`确认删除用户 ${u.username}？`, "删除用户", { type: "warning" });
        await api(`/api/users/${u.id}`, { method: "DELETE" });
        toast.ok("已删除"); loadUsers();
      } catch (e) { if (e !== "cancel" && e?.message) toast.err(e); }
    }

    function loadAll() {
      loadProjects(); loadRuns(); loadConfig(); loadTools();
      if (isAdmin.value) loadUsers();
    }
    function onTabChange(name) {
      if (name === "home") loadTools();
      else if (name === "projects") loadProjects();
      else if (name === "runs") loadRuns();
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
      user, loading, acting, loginError, loginForm, authBackend, ssoLogin, tab, isAdmin,
      projects, loadingProjects, runs, loadingRuns, runFilter,
      harnesses, components, componentList, prompts,
      tools, loadingTools, groupedTools, users, newUser,
      showNewProject, newProject, showOverrides, editProject, overridesText,
      showTrigger, triggerForm, showLog, logRunId, logText, showReport, reportRunId, reportText,
      fmtTime, open, projectName, runStatusText, runTagType, toolStatusText,
      login, logout, onTabChange,
      loadProjects, createProject, syncProject, openOverrides, saveOverrides,
      loadRuns, openTrigger, triggerRun, openLog, openReport, stopLogPoll,
      loadTools, ctlTool, createUser, removeUser,
    };
  },
}).use(ElementPlus).mount("#app");

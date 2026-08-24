/* AISystem Manager 前端逻辑（Vue3 全局构建，无打包步骤） */
const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

createApp({
  setup() {
    const user = ref(null);
    const loading = ref(false);
    const loginError = ref("");
    const tab = ref("tools");

    const tools = ref([]);
    const loadingTools = ref(false);

    const sessions = ref([]);
    const loadingSessions = ref(false);
    const currentSession = ref("");
    const screenText = ref("");
    const cmdText = ref("");
    const acting = ref(false);
    const autoRefresh = ref(false);
    const newSession = ref({ id: "", command: "bash", purpose: "" });
    let refreshTimer = null;

    const isBoss = computed(() => (user.value?.groups || []).includes("boss"));
    const groupedTools = computed(() => {
      const g = {};
      for (const t of tools.value) (g[t.group || "其他"] ||= []).push(t);
      return g;
    });

    async function api(path, opts = {}) {
      const resp = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...opts,
      });
      if (resp.status === 401) { user.value = null; throw new Error("未登录"); }
      if (!resp.ok) {
        let msg = resp.statusText;
        try { msg = (await resp.json()).detail || msg; } catch (_) {}
        throw new Error(msg);
      }
      const ct = resp.headers.get("content-type") || "";
      return ct.includes("json") ? resp.json() : resp.text();
    }

    function login() { window.location.href = "/api/auth/login"; }
    function logout() { window.location.href = "/api/auth/logout"; }
    function open(url) { window.open(url, "_blank"); }

    function statusText(t) {
      return { running: "运行中", stopped: "已停止", absent: "未部署", external: "外部", unknown: "未知" }[t.status] || t.status;
    }

    async function loadMe() {
      try { user.value = await api("/api/auth/me"); } catch (_) { user.value = null; }
    }
    async function loadTools() {
      loadingTools.value = true;
      try { tools.value = await api("/api/tools"); }
      catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { loadingTools.value = false; }
    }
    async function ctl(t, action) {
      try {
        await api(`/api/tools/${t.name}/${action}`, { method: "POST" });
        ElementPlus.ElMessage.success(`${t.name} ${action} 已执行`);
        setTimeout(loadTools, 1500);
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
    }

    async function loadSessions() {
      loadingSessions.value = true;
      try {
        const r = await api("/api/agent/sessions");
        sessions.value = Array.isArray(r) ? r : (r.sessions || []);
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { loadingSessions.value = false; }
    }
    async function createSession() {
      if (!newSession.value.id) { ElementPlus.ElMessage.warning("请填写会话 ID"); return; }
      acting.value = true;
      try {
        await api("/api/agent/sessions", { method: "POST", body: JSON.stringify(newSession.value) });
        ElementPlus.ElMessage.success("会话已创建");
        await loadSessions();
        selectSession(newSession.value.id);
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { acting.value = false; }
    }
    async function removeSession(id) {
      try {
        await api(`/api/agent/sessions/${id}`, { method: "DELETE" });
        if (currentSession.value === id) { currentSession.value = ""; screenText.value = ""; }
        await loadSessions();
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
    }
    function selectSession(id) { currentSession.value = id; refreshScreen(); }
    async function refreshScreen() {
      if (!currentSession.value) return;
      try { screenText.value = await api(`/api/agent/sessions/${currentSession.value}/screenshot`); }
      catch (e) { screenText.value = `（获取失败: ${e.message}）`; }
    }
    async function submitCmd() {
      if (!cmdText.value.trim()) return;
      try {
        await api(`/api/agent/sessions/${currentSession.value}/actions`, {
          method: "POST", body: JSON.stringify({ type: "submit", text: cmdText.value }),
        });
        cmdText.value = "";
        setTimeout(refreshScreen, 600);
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
    }
    async function sendKey(key) {
      await api(`/api/agent/sessions/${currentSession.value}/actions`, {
        method: "POST", body: JSON.stringify({ type: "key", key }),
      }).catch(e => ElementPlus.ElMessage.error(e.message));
      setTimeout(refreshScreen, 400);
    }
    async function sendControl(key) {
      await api(`/api/agent/sessions/${currentSession.value}/actions`, {
        method: "POST", body: JSON.stringify({ type: "control", key }),
      }).catch(e => ElementPlus.ElMessage.error(e.message));
      setTimeout(refreshScreen, 400);
    }
    async function waitStable() {
      try {
        await api(`/api/agent/sessions/${currentSession.value}/wait`, {
          method: "POST", body: JSON.stringify({ until: "screen_stable", timeout_ms: 10000, stable_ms: 800 }),
        });
        ElementPlus.ElMessage.success("屏幕已稳定");
        refreshScreen();
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
    }

    onMounted(async () => {
      await loadMe();
      if (user.value) { loadTools(); loadSessions(); }
      refreshTimer = setInterval(() => { if (autoRefresh.value) refreshScreen(); }, 2000);
    });
    onUnmounted(() => clearInterval(refreshTimer));

    return {
      user, loading, loginError, tab, isBoss,
      tools, loadingTools, groupedTools, statusText, open, ctl, loadTools,
      sessions, loadingSessions, currentSession, screenText, cmdText, acting, autoRefresh, newSession,
      login, logout, loadSessions, createSession, removeSession, selectSession,
      refreshScreen, submitCmd, sendKey, sendControl, waitStable,
    };
  },
}).use(ElementPlus).mount("#app");

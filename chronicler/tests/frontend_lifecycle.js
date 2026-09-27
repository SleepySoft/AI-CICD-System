/* 可在 Node 或独立 JavaScript 引擎执行；注入 app.js 文本，不依赖 Vue/浏览器安装。 */
async function verifyFrontendLifecycle(source) {
  const pending = [], messages = [];
  let state, confirmations = 0;
  const Vue = {
    ref: value => ({ value }), computed: getter => ({ get value() { return getter(); } }),
    onMounted() {}, onUnmounted() {},
    createApp(options) {
      state = options.setup();
      return { component() {}, use() { return this; }, mount() {} };
    },
  };
  const ElementPlus = {
    ElMessage: { success: x => messages.push(x), error: x => messages.push(x), warning() {} },
    ElMessageBox: { confirm: async () => { confirmations++; } },
  };
  const fetch = (path, options) => new Promise(resolve => pending.push({ path, options, resolve }));
  const respond = (request, data) => request.resolve({ ok: true, status: 200,
    headers: { get: () => 'application/json' }, json: async () => data });
  const tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
  const assert = (condition, name) => { if (!condition) throw new Error(name); };
  new Function('Vue', 'ElementPlus', 'ElementPlusIconsVue', 'fetch', 'window', 'document',
    'location', 'setTimeout', 'clearTimeout', 'URLSearchParams', source)(Vue, ElementPlus, {}, fetch,
    { addEventListener() {} }, { hidden: false }, { hash: '' }, () => 1, () => {},
    class { constructor(values) { this.values = values; }
      toString() { return Object.entries(this.values).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&'); } });

  // 较早发出的慢列表请求不能覆盖较新的筛选结果。
  state.runFilter.value = 1;
  const oldLoad = state.loadRuns();
  state.runFilter.value = 2;
  const newLoad = state.loadRuns();
  respond(pending[1], [{ id: 2 }]); await newLoad;
  respond(pending[0], [{ id: 1 }]); await oldLoad;
  assert(state.runs.value[0].id === 2, 'stale list replaced latest filter');
  pending.length = 0;

  // 预览等待期连续点击只提交一次；离开页面后迟到响应不改变导航。
  state.tab.value = 'projects';
  const task = { id: 7, name: 'task', project_id: 1, task_type: 'operational_reporter' };
  const first = state.triggerTask(task);
  await state.triggerTask(task);
  assert(pending.length === 1, 'duplicate preview request');
  respond(pending[0], { change_summary: { state: 'changed' } }); await tick();
  assert(pending.length === 2 && confirmations === 1, 'duplicate trigger submission');
  assert(pending[1].options.headers['Idempotency-Key'], 'missing idempotency key');
  state.tab.value = 'config';
  respond(pending[1], { id: 9 }); await tick();
  for (const request of pending.slice(2)) respond(request, []);
  await first;
  assert(state.tab.value === 'config', 'delayed completion changed navigation');
  assert(!state.taskTriggerBusy(task), 'pending task stayed locked');
  pending.length = 0;

  // 确认期间修改表单不能改变已经确认的任务参数。
  state.triggerForm.value = { project_id: 1, task_type: 'operational_reporter', extra_prompt: 'original' };
  const direct = state.triggerRun();
  state.triggerForm.value.extra_prompt = 'edited';
  state.runFilter.value = 3;
  respond(pending[0], { change_summary: { state: 'changed' } }); await tick();
  assert(JSON.parse(pending[1].options.body).extra_prompt === 'original', 'mutable payload submitted');
  respond(pending[1], { id: 10 }); await tick();
  for (const request of pending.slice(2)) respond(request, []);
  await direct;
  assert(state.runFilter.value === 3, 'delayed completion replaced selected project');
  assert(!state.triggeringRun.value, 'direct submit stayed locked');
  return 'PASS: stale lists, duplicate clicks, delayed navigation, immutable payload';
}
if (typeof module !== 'undefined') module.exports = verifyFrontendLifecycle;

/* Read-only local project dashboard. No operational mutations or remote assets. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = { projects: [], project: null, snapshot: null, filter: 'all', search: '', request: 0, busy: false, error: null, lastSuccess: null, executor: null };
  const labels = { active:'进行中', running:'进行中', starting:'启动中', queued:'排队中', pending:'待处理', waiting:'等待中', blocked:'受阻', failed:'失败', completed:'执行结束', done:'执行结束', finished:'执行结束', accepted:'已验收', rejected:'未通过', cancelled:'已取消', canceled:'已取消', interrupted:'已中断', unknown:'未知', 'saved binding':'已保存绑定', saved_binding:'已保存绑定', bound:'已绑定', idle:'空闲', needs_review:'待验收', review:'待验收', passed:'通过', success:'通过', error:'错误', reserved:'已预留', initializing:'初始化中', waiting_for_input:'等待输入', recovery_required:'需要恢复', verified:'已验证', checks_failed:'检查失败', verification_failed:'验证失败', preparation_failed:'准备失败', timed_out:'已超时', superseded:'已被替代', noticed:'已接收通知' };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const list = value => Array.isArray(value) ? value : [];
  const str = value => value === null || value === undefined || value === '' ? '未记录' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const category = value => /^(active|running|starting|in_progress|reserved|initializing)$/.test(value) ? 'active' : /^(blocked|failed|error|rejected|interrupted|recovery_required|checks_failed|verification_failed|preparation_failed|timed_out)$/.test(value) ? 'blocked' : /^(completed|done|finished|accepted|succeeded|verified|passed|success)$/.test(value) ? 'completed' : /^(waiting|pending|queued|needs_review|review|waiting_for_input|noticed)$/.test(value) ? 'waiting' : 'unknown';
  const badge = value => `<span class="badge ${category(value)}">${escape(labels[value] || value || '未知')}</span>`;
  function date(value, full = false) {
    if (!value) return '未记录';
    const d = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
    if (Number.isNaN(d.getTime())) return '时间未知';
    return new Intl.DateTimeFormat('zh-CN', full ? {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false} : {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);
  }
  function safeURL(value, localOnly = false) {
    if (!value || typeof value !== 'string') return null;
    try { const url = new URL(value, location.origin); if (!['http:', 'https:'].includes(url.protocol)) return null; if (localOnly && url.origin !== location.origin) return null; return url.href; } catch { return null; }
  }
  function empty(title, description = '') { return `<div class="empty-state"><strong>${escape(title)}</strong>${description ? `<p>${escape(description)}</p>` : ''}</div>`; }
  function notice() {
    const messages = [];
    if (state.error) messages.push(state.error);
    if (state.snapshot?.stale) messages.push('本地状态已过期。以下内容保留最后记录，不代表当前执行状态。');
    const provenanceWarnings = new Set([
      'Live worker and coordinator liveness is unknown. Counts reflect saved local state, not verified running processes.',
      'Tasks include locally saved jobs and notifier entries; this is not a live GitHub board.'
    ]);
    list(state.snapshot?.warnings).forEach(item => { const message = typeof item === 'string' ? item : str(item.message || item); if (!provenanceWarnings.has(message)) messages.push(message); });
    if (state.snapshot?.available === false) messages.push('此项目尚无可读取的运行记录。');
    $('notice').innerHTML = messages.length ? `<div class="notice ${state.error ? 'error' : ''}">${messages.map(escape).join('<br>')}</div>` : '';
    $('connection').textContent = state.error ? '连接异常 · 保留记录' : state.busy ? '正在刷新' : state.lastSuccess ? '本地数据已同步' : '等待数据';
  }
  function renderProjects() {
    $('project-count').textContent = state.projects.length;
    const markup = state.projects.length ? state.projects.map(project => `<button class="project-link ${project.id === state.project ? 'active' : ''}" type="button" data-project="${escape(project.id)}" ${project.id === state.project ? 'aria-current="page"' : ''} title="${escape(project.name)}"><span class="project-symbol" aria-hidden="true">▤</span><span class="project-link-text">${escape(project.name || project.id)}</span></button>`).join('') : '<p class="muted small">尚未配置项目</p>';
    if (state.projectMarkup !== markup) { $('projects').innerHTML = markup; state.projectMarkup = markup; }
  }
  const taskExecutors = task => list(state.snapshot?.executors).filter(executor => String(executor.task_id) === String(task.id)).map(executor => executor.id);
  function taskRows() {
    const tasks = list(state.snapshot?.tasks).filter(task => (state.filter === 'all' || category(task.status) === state.filter) && `${task.id} ${task.title} ${task.assignee || ''} ${taskExecutors(task).join(' ')}`.toLocaleLowerCase().includes(state.search.toLocaleLowerCase()));
    $('task-rows').innerHTML = tasks.length ? tasks.map(task => {
      const url = safeURL(task.url || task.issue_url);
      return `<div class="task-row" role="row"><div role="cell"><div class="task-name">${url ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(task.title || task.id)} ↗</a>` : escape(task.title || task.id)}</div><div class="task-id">${escape(task.id)}${list(task.dependencies).length ? ` · 依赖 ${escape(task.dependencies.join(', '))}` : ''}</div></div><div role="cell">${badge(task.status)}</div><div class="task-executor" role="cell">${escape(task.assignee || task.executor_id || taskExecutors(task).join(', ') || '未分配')}</div><div class="task-updated" role="cell">${escape(date(task.updated_at))}</div></div>`;
    }).join('') : empty(list(state.snapshot?.tasks).length ? '没有匹配的任务' : '还没有任务记录', list(state.snapshot?.tasks).length ? '试试其他筛选条件或搜索词' : 'coordinator 记录的任务会显示在这里');
    document.querySelectorAll('.filter').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === state.filter)));
  }
  function render() {
    const data = state.snapshot;
    if (!data) return;
    const project = data.project || state.projects.find(project => project.id === state.project) || {};
    $('project-title').textContent = project.name || '项目工作台';
    $('breadcrumb-project').textContent = project.name || state.project;
    $('project-description').textContent = project.repository || project.workspace || '本地任务、执行会话与验收记录';
    $('last-update').textContent = '本地状态快照 · 每 5 秒刷新';
    $('last-update').title = `最近读取：${date(state.lastSuccess, true)}`;
    document.title = `${project.name || '项目工作台'} · Project Delegation`;
    const summary = data.summary || {};
    const co = data.coordinator || {};
    const executors = list(data.executors);
    const events = list(data.events);
    const reports = list(data.reports);
    const count = key => summary[key] === undefined || summary[key] === null ? '—' : escape(summary[key]);
    $('content').innerHTML = `
      <section class="stats" aria-label="项目统计">
        <article class="stat"><div class="stat-label">活跃执行器 <span class="stat-icon" aria-hidden="true">◉</span></div><div class="stat-value">${count('active')} <small>/ ${count('limit')}</small></div><div class="stat-note">状态记录</div></article>
        <article class="stat"><div class="stat-label">等待推进 <span class="stat-icon" aria-hidden="true">◷</span></div><div class="stat-value">${count('waiting')}</div><div class="stat-note">等待继续执行或人工输入</div></article>
        <article class="stat"><div class="stat-label">需要关注 <span class="stat-icon" aria-hidden="true">⊘</span></div><div class="stat-value">${count('blocked')}</div><div class="stat-note">受阻或失败的任务</div></article>
        <article class="stat"><div class="stat-label">执行结束 <span class="stat-icon" aria-hidden="true">✓</span></div><div class="stat-value">${count('completed')}</div><div class="stat-note">是否验收以任务状态为准</div></article>
      </section>
      <section class="coordinator" aria-label="项目协调会话"><div class="coordinator-icon" aria-hidden="true">⌘</div><div class="coordinator-body"><div class="coordinator-title">项目 Coordinator ${badge(co.status)}</div><p>原生会话负责规划、分派与验收 · 实时连接状态${co.live_status && co.live_status !== 'unknown' ? `：${escape(co.live_status)}` : '未验证'}</p><p class="mono">${escape(co.thread_id || co.session_id || '尚未记录 coordinator 会话')}</p></div><div class="coordinator-meta">最近绑定验证<br>${escape(date(co.verified_at || co.updated_at))}</div></section>
      <section class="tasks-section" aria-labelledby="tasks-title"><div class="section-heading"><h2 id="tasks-title">任务 <small>${list(data.tasks).length}</small></h2><span class="section-caption">从分派到验收，查看每一步进展</span></div><div class="task-controls"><div class="filters" role="group" aria-label="按任务状态筛选">${[['all','全部'],['active','进行中'],['waiting','等待中'],['blocked','受阻'],['completed','已结束']].map(([key,label]) => `<button class="filter" data-filter="${key}" type="button" aria-pressed="${state.filter === key}">${label}</button>`).join('')}</div><label class="search"><span aria-hidden="true">⌕</span><input id="task-search" type="search" placeholder="搜索任务或执行器…" aria-label="搜索任务或执行器" value="${escape(state.search)}"></label></div><div class="task-table" role="table" aria-label="项目任务"><div class="table-head" role="row"><div role="columnheader">任务</div><div role="columnheader">状态</div><div role="columnheader">执行器</div><div role="columnheader">最近更新</div></div><div id="task-rows" role="rowgroup"></div></div></section>
      <div class="lower-grid"><div><section aria-labelledby="executors-title"><div class="section-heading"><h2 id="executors-title">执行会话 <small>${executors.length}</small></h2><span class="section-caption">独立会话 · 明确的文件归属</span></div>${executors.length ? `<div class="executors-grid">${executors.map((executor,index) => `<button class="executor-card" type="button" data-executor="${escape(executor.id)}" aria-label="查看 ${escape(executor.title || executor.id)} 执行会话详情"><div class="executor-top"><span class="executor-avatar" aria-hidden="true">${String(index+1).padStart(2,'0')}</span>${badge(executor.status)}</div><h3>${escape(executor.title || executor.id)}</h3><p class="mono">${escape(executor.id)}</p><div class="executor-footer"><span>${list(executor.owned_paths).length} 项路径归属 · ${list(executor.checks).length} 项检查记录</span><span class="detail-arrow" aria-hidden="true">↗</span></div></button>`).join('')}</div>` : empty('还没有执行会话','分派后的持久化 executor 记录会显示在这里')}</section>
      <section class="reports-section" aria-labelledby="reports-title"><div class="section-heading"><h2 id="reports-title">报告与产物 <small>${reports.length}</small></h2><span class="section-caption">本地文件 · 下载后查看</span></div>${reports.length ? reports.map(report => { const url = safeURL(report.url, true); return url ? `<a class="report-link" href="${escape(url)}" download><span aria-hidden="true">▧</span><span>${escape(report.title || report.name || report.id)}</span><span aria-label="下载">↓</span></a>` : `<div class="report-link"><span aria-hidden="true">▧</span><span>${escape(report.title || report.name || report.id)}</span><span>链接不可用</span></div>`; }).join('') : empty('暂无报告','可下载的报告会出现在这里')}</section></div>
      <section aria-labelledby="events-title"><div class="section-heading"><h2 id="events-title">最近动态 <small>${events.length}</small></h2><span class="section-caption">基于本地记录</span></div>${events.length ? `<div class="timeline-panel"><ol class="timeline">${events.slice(0,12).map(event => `<li><div class="timeline-message">${escape(event.message || event.title || event.type || '状态更新')}</div><time>${escape(date(event.timestamp || event.updated_at,true))}${event.executor_id ? ` · ${escape(event.executor_id)}` : ''}</time></li>`).join('')}</ol></div>` : empty('暂无动态记录','这里只展示有来源的事件')}</section></div>`;
    $('content').setAttribute('aria-busy','false');
    taskRows();
    if (state.executor && $('executor-dialog').open) renderDrawer(state.executor);
    notice();
  }
  function renderDrawer(id) {
    const executor = list(state.snapshot?.executors).find(item => String(item.id) === String(id));
    if (!executor) { $('drawer-content').innerHTML = empty('此会话已不在当前快照中','关闭详情后刷新项目'); return; }
    const report = safeURL(executor.report_url, true);
    const result = executor.result_summary || executor.result;
    if (!executor.title && !executor.id) return;
    $('drawer-content').innerHTML = `${badge(executor.status)}<h2 id="drawer-title">${escape(executor.title || executor.id)}</h2><dl class="detail-list">${[['执行器',executor.id],['关联任务',executor.task_id],['原生会话',executor.session_id || executor.thread_id],['工作目录',executor.workspace || executor.worktree],['最近更新',date(executor.updated_at,true)],['执行回执状态',executor.executor_status ? (labels[executor.executor_status] || executor.executor_status) : undefined],['回执来源',executor.receipt ? (executor.receipt.status === 'unavailable' ? '回执缺失或不可读取' : executor.receipt.stale ? '缓存记录 · 已过期' : executor.receipt.status === 'ok' ? '本地回执文件' : '回执状态未知') : undefined]].map(([label,value]) => `<div><dt>${label}</dt><dd class="mono">${escape(str(value))}</dd></div>`).join('')}</dl><section class="drawer-section"><h3>路径归属</h3>${list(executor.owned_paths).length ? `<ul class="path-list">${executor.owned_paths.map(path => `<li class="mono">${escape(str(path))}</li>`).join('')}</ul>` : '<p class="muted small">未记录路径归属</p>'}</section><section class="drawer-section"><h3>检查记录</h3>${list(executor.checks).length ? `<ul class="path-list">${executor.checks.map(check => `<li>${typeof check === 'object' ? `${escape(check.name || check.command || '检查')} ${badge(check.status || (check.returncode === 0 || check.passed === true ? 'passed' : check.passed === false || typeof check.returncode === 'number' ? 'failed' : 'unknown'))}` : escape(check)}</li>`).join('')}</ul>` : '<p class="muted small">暂无检查记录；不能据此认定检查通过</p>'}</section><section class="drawer-section"><h3>结果摘要</h3>${result ? `<div class="result-text">${escape(str(result))}</div>` : '<p class="muted small">暂无可展示的结果摘要</p>'}${report ? `<a class="report-link" href="${escape(report)}" download>下载本地报告 <span>↓</span></a>` : ''}</section>`;
  }
  async function getJSON(path) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try { const response = await fetch(path, {signal:controller.signal,cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}}); if (!response.ok) throw new Error(`HTTP ${response.status}`); return await response.json(); } finally { clearTimeout(timeout); }
  }
  async function refresh(force = false) {
    if (state.busy && !force) return;
    const token = ++state.request;
    state.busy = true; $('refresh').disabled = true; notice();
    try {
      const catalog = await getJSON('/api/projects');
      if (token !== state.request) return;
      state.projects = list(catalog.projects);
      if (!state.projects.some(project => String(project.id) === state.project)) {
        state.project = state.projects.length ? String(state.projects[0].id) : null;
        state.snapshot = null; state.executor = null; $('executor-dialog').close();
      }
      renderProjects();
      if (!state.project) { state.snapshot = null; state.error = null; state.lastSuccess = new Date().toISOString(); $('content').innerHTML = empty('尚未配置项目','启动工作台时添加项目配置，即可在这里查看任务与执行会话'); $('content').setAttribute('aria-busy','false'); return; }
      const snapshot = await getJSON(`/api/projects/${encodeURIComponent(state.project)}`);
      if (token !== state.request) return;
      if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) throw new Error('无效的数据响应');
      state.snapshot = snapshot; state.error = null; state.lastSuccess = new Date().toISOString();
      const focused = document.activeElement;
      const restore = focused?.id === 'task-search' ? {id:'task-search', selection:[focused.selectionStart,focused.selectionEnd]} : focused?.dataset.filter ? {filter:focused.dataset.filter} : focused?.dataset.executor ? {executor:focused.dataset.executor} : focused?.tagName === 'A' && focused.closest('#content, #drawer-content') ? {href:focused.href, drawer:!!focused.closest('#drawer-content')} : null;
      render();
      if (restore) {
        const target = restore.id ? $(restore.id) : restore.href ? [...document.querySelectorAll(restore.drawer ? '#drawer-content a' : '#content a')].find(link => link.href === restore.href) : [...document.querySelectorAll(restore.filter ? '[data-filter]' : '[data-executor]')].find(button => restore.filter ? button.dataset.filter === restore.filter : button.dataset.executor === restore.executor);
        if (target) { target.focus({preventScroll:true}); if (restore.selection) target.setSelectionRange(...restore.selection); }
      }
    } catch (error) {
      if (token !== state.request) return;
      state.error = `无法读取本地项目数据（${error.name === 'AbortError' ? '请求超时' : error.message}）。${state.snapshot ? '保留上次成功读取的记录；稍后会自动重试。' : '请确认本地服务与项目配置可用，稍后会自动重试。'}`;
      if (!state.snapshot) { $('content').innerHTML = empty('项目数据暂时不可用','点击右上角刷新，或等待自动重试'); $('content').setAttribute('aria-busy','false'); }
    } finally { if (token === state.request) { state.busy = false; $('refresh').disabled = false; notice(); } }
  }
  $('projects').addEventListener('click', event => { const button = event.target.closest('[data-project]'); if (!button || button.dataset.project === state.project) return; state.project = button.dataset.project; state.snapshot = null; state.filter = 'all'; state.search = ''; state.executor = null; $('executor-dialog').close(); history.replaceState(null,'',`?project=${encodeURIComponent(state.project)}`); $('content').innerHTML = '<div class="loading-state"><span class="spinner"></span><h2>正在读取项目</h2></div>'; $('content').setAttribute('aria-busy','true'); renderProjects(); refresh(true); });
  $('content').addEventListener('click', event => { const filter = event.target.closest('[data-filter]'); if (filter) { state.filter = filter.dataset.filter; taskRows(); } const executor = event.target.closest('[data-executor]'); if (executor) { state.executor = executor.dataset.executor; renderDrawer(state.executor); $('executor-dialog').showModal(); } });
  $('content').addEventListener('input', event => { if (event.target.id === 'task-search') { state.search = event.target.value; taskRows(); } });
  $('refresh').addEventListener('click', () => refresh());
  $('close-drawer').addEventListener('click', () => $('executor-dialog').close());
  $('executor-dialog').addEventListener('click', event => { if (event.target === $('executor-dialog')) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
  $('executor-dialog').addEventListener('close', () => { const id = state.executor; state.executor = null; const button = [...document.querySelectorAll('[data-executor]')].find(button => button.dataset.executor === id); if (button) button.focus({preventScroll:true}); });
  try { const theme = localStorage.getItem('delegation-theme'); if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme; } catch {}
  $('theme-toggle').addEventListener('click', () => { const dark = document.documentElement.dataset.theme === 'dark' || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches); document.documentElement.dataset.theme = dark ? 'light' : 'dark'; try { localStorage.setItem('delegation-theme', dark ? 'light' : 'dark'); } catch {} });
  state.project = new URLSearchParams(location.search).get('project');
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); },5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();

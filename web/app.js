/* Read-only local project dashboard. No operational mutations or remote assets. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = { projects: [], project: null, snapshot: null, filter: 'all', search: '', request: 0, busy: false, error: null, lastSuccess: null, executor: null, report: null, reportRequest: 0, reportController: null, loadedReport: null, loadingReport: null, attemptedReport: null };
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
  // Source links come from validated API fields; never infer task or revision metadata.
  function githubURL(value) {
    const url = safeURL(value);
    if (!url) return null;
    const parsed = new URL(url);
    return parsed.protocol === 'https:' && parsed.hostname === 'github.com' && !parsed.port && !parsed.username && !parsed.password ? url : null;
  }
  function reportURL(report, preview = false) {
    const url = safeURL(report?.[preview ? 'preview_url' : 'url'], true);
    if (!url || !state.project || !report?.id) return null;
    const parsed = new URL(url);
    return parsed.pathname === `/${preview ? 'preview' : 'reports'}/${encodeURIComponent(state.project)}/${encodeURIComponent(report.id)}` && !parsed.search && !parsed.hash && !parsed.username && !parsed.password ? url : null;
  }
  const reportName = report => report.title || report.name || report.id;
  const reportVersion = report => `${report.updated_at || ''}/${report.size ?? ''}`;
  const projectURL = () => `?project=${encodeURIComponent(state.project || '')}`;
  const currentReport = () => list(state.snapshot?.reports).find(report => String(report.id) === state.report);
  function reportCard(report, compact = false) {
    const download = reportURL(report);
    const preview = reportURL(report, true);
    const title = escape(reportName(report));
    return `<div class="report-card ${compact ? 'compact' : ''}"><span class="report-file-icon" aria-hidden="true">▧</span><div class="report-card-body">${preview ? `<button class="report-open" type="button" data-report="${escape(report.id)}">${title}</button>` : download ? `<a class="report-open" href="${escape(download)}" download>${title}</a>` : `<span>${title}</span>`}<div class="report-card-meta">${escape(report.format?.toUpperCase() || '文件')} · ${escape(date(report.updated_at))}${report.task_title ? ` · ${escape(report.task_title)}` : ''}</div></div>${preview ? `<button type="button" class="report-read" data-report="${escape(report.id)}" aria-label="阅读 ${title}">阅读 <span aria-hidden="true">↗</span></button>` : download ? `<a class="report-download" href="${escape(download)}" download aria-label="下载 ${title}">↓</a>` : '<span class="muted small">不可用</span>'}</div>`;
  }
  function taskReports(task) {
    return list(task.report_ids).map(id => list(state.snapshot?.reports).find(report => String(report.id) === String(id))).filter(Boolean);
  }
  function reportButtons(reports) {
    return reports.map(report => reportURL(report, true) ? `<button type="button" class="task-report" data-report="${escape(report.id)}">▧ ${escape(reportName(report))}</button>` : '').join('');
  }
  function cancelReport() {
    state.reportRequest++;
    state.reportController?.abort();
    clearTimeout(state.reportLoadTimer);
    state.reportController = null;
    $('report-canvas').replaceChildren();
    $('report-canvas').setAttribute('aria-busy', 'false');
    state.loadedReport = null;
    state.loadingReport = null;
  }
  function restoreReportFocus() {
    const origin = state.reportOrigin;
    const selector = origin?.executor ? '[data-executor]' : '[data-report]';
    const target = [...document.querySelectorAll(selector)].find(button => origin?.executor ? button.dataset.executor === origin.executor : button.dataset.report === origin?.report);
    (target || $('project-title')).focus({preventScroll:true});
    state.reportOrigin = null;
  }
  function exitReader(restore = true) {
    const wasOpen = !$('report-reader').hidden;
    cancelReport();
    $('report-reader').hidden = true;
    $('overview').hidden = false;
    $('main').classList.remove('reading');
    state.readerMarkup = null;
    if (wasOpen && restore) restoreReportFocus();
  }
  function readerStatus(title, description, retry = false) {
    $('reader-status').innerHTML = title ? `<div class="empty-state"><strong>${escape(title)}</strong><p>${escape(description)}</p>${retry ? '<button id="retry-report" type="button" class="text-button">重新加载</button>' : ''}</div>` : '';
  }
  async function loadReport(report) {
    const url = reportURL(report, true);
    cancelReport();
    if (!url) { readerStatus('此文件暂不支持在线阅读', '可以下载原文件，或选择另一份 HTML 报告'); return; }
    const token = state.reportRequest;
    const controller = new AbortController();
    state.reportController = controller;
    state.loadingReport = `${state.project}/${report.id}`;
    const timeout = setTimeout(() => controller.abort(), 12000);
    $('report-canvas').setAttribute('aria-busy', 'true');
    $('reader-update').hidden = true;
    readerStatus('正在读取报告', '正在加载本地文件…');
    try {
      const response = await fetch(url, {method:'HEAD', signal:controller.signal, cache:'no-store', credentials:'same-origin', headers:{Accept:'text/html'}});
      if (!response.ok) throw new Error(response.status === 404 ? '报告已移除或不可读取' : `HTTP ${response.status}`);
      if (!(response.headers.get('Content-Type') || '').toLowerCase().startsWith('text/html')) throw new Error('报告格式不正确');
      if (token !== state.reportRequest) return;
      const frame = document.createElement('iframe');
      frame.setAttribute('sandbox', '');
      frame.setAttribute('referrerpolicy', 'no-referrer');
      frame.setAttribute('title', reportName(report));
      frame.className = 'report-frame';
      frame.addEventListener('load', () => {
        if (token !== state.reportRequest) return;
        clearTimeout(state.reportLoadTimer);
        state.loadedReport = {key:`${state.project}/${report.id}`, version:reportVersion(report)};
        readerStatus('', '');
        $('report-canvas').setAttribute('aria-busy', 'false');
      });
      const failedFrame = () => {
        if (token !== state.reportRequest) return;
        cancelReport();
        readerStatus('报告暂时无法打开', '报告加载超时或连接中断，可以重试或下载原文件', true);
      };
      frame.addEventListener('error', failedFrame);
      state.reportLoadTimer = setTimeout(failedFrame, 12000);
      // A real document URL keeps the preview's CSP independent of the stricter
      // dashboard policy. srcdoc would inherit its inline-style prohibition.
      // HEAD checks ordinary HTTP failures; the iframe still has no sandbox grants.
      frame.src = url;
      $('report-canvas').replaceChildren(frame);
    } catch (error) {
      if (token !== state.reportRequest) return;
      readerStatus('报告暂时无法打开', `${error.name === 'AbortError' ? '读取超时，请稍后重试' : error.message}。你也可以下载原文件`, true);
      $('report-canvas').setAttribute('aria-busy', 'false');
    } finally {
      clearTimeout(timeout);
      if (token === state.reportRequest) { state.reportController = null; state.loadingReport = null; }
    }
  }
  function syncReader() {
    if (!state.report) { exitReader(false); return; }
    const opening = $('report-reader').hidden;
    $('overview').hidden = true;
    $('report-reader').hidden = false;
    $('main').classList.add('reading');
    const project = state.snapshot?.project || {};
    const report = currentReport();
    const reports = list(state.snapshot?.reports);
    const issue = githubURL(report?.issue_url);
    const repository = githubURL(project.repository_url);
    const download = reportURL(report);
    const title = report ? reportName(report) : '报告不可用';
    const actions = `${issue || repository ? `<a class="text-button" href="${escape(issue || repository)}" target="_blank" rel="noopener noreferrer">${issue ? 'GitHub 任务' : 'GitHub 仓库'} ↗</a>` : ''}${download ? `<a class="text-button" href="${escape(download)}" download>下载原文件 ↓</a>` : ''}`;
    const metadata = report ? [report.source === 'acceptance' ? '验收报告' : '本地报告', report.task_title, `更新于 ${date(report.updated_at, true)}`, typeof report.size === 'number' ? `${Math.max(1, Math.ceil(report.size / 1024))} KB` : null].filter(Boolean).map(escape).join(' · ') : '该文件已移除、不可访问，或不在当前项目中';
    const heading = `<div class="reader-heading-copy"><div class="eyebrow">${escape(project.name || state.project)}</div><h1 id="reader-title" tabindex="-1">${escape(title)}</h1><p>${metadata}</p></div>${reports.length > 1 ? `<details class="report-history"><summary>项目报告 <span>${reports.length}</span></summary><div class="report-history-list" aria-label="项目中已有的报告">${reports.map(item => `<div${String(item.id) === state.report ? ' class="current-report"' : ''}>${reportCard(item, true)}</div>`).join('')}<p>列出当前保存的文件，不代表同一报告的版本历史</p></div></details>` : ''}`;
    const markup = `${actions}\n${heading}`;
    if (state.readerMarkup !== markup) {
      const historyOpen = document.querySelector('.report-history')?.open;
      $('reader-actions').innerHTML = actions;
      $('reader-heading').innerHTML = heading;
      const history = document.querySelector('.report-history');
      if (history && historyOpen) history.open = true;
      state.readerMarkup = markup;
    }
    $('breadcrumb-project').textContent = `${project.name || state.project} / 报告`;
    document.title = `${title} · Project Delegation`;
    if (!report) {
      cancelReport();
      state.attemptedReport = null;
      $('reader-update').hidden = true;
      readerStatus('找不到这份报告', '返回项目或从项目报告中选择其他文件');
    } else {
      const key = `${state.project}/${report.id}`;
      if (state.loadedReport?.key === key) {
        const changed = state.loadedReport.version !== reportVersion(report);
        $('reader-update').hidden = !changed;
        $('reader-update').innerHTML = changed ? '本地文件已更新。当前保留你正在阅读的内容 <button id="reload-report" class="text-button" type="button">读取最新内容</button>' : '';
      } else if (state.loadingReport !== key && state.attemptedReport !== key) {
        state.attemptedReport = key;
        loadReport(report);
      }
    }
    if (opening) { $('reader-title').focus({preventScroll:true}); window.scrollTo({top:0, behavior:'instant'}); }
  }
  function openReport(id, origin = null) {
    if (!list(state.snapshot?.reports).some(report => String(report.id) === String(id))) return;
    const wasOpen = !!state.report;
    if (!wasOpen) state.reportOrigin = origin || {report:String(id)};
    if ($('executor-dialog').open) $('executor-dialog').close();
    if (state.report !== String(id)) { cancelReport(); state.attemptedReport = null; }
    state.report = String(id);
    const url = `${projectURL()}&report=${encodeURIComponent(state.report)}`;
    if (wasOpen) history.replaceState(history.state, '', url);
    else history.pushState({readerEntry:true}, '', url);
    syncReader();
    const historyMenu = document.querySelector('.report-history');
    if (historyMenu) historyMenu.open = false;
    $('reader-title').focus({preventScroll:true});
  }
  function closeReader() {
    if (history.state?.readerEntry) { history.back(); return; }
    state.report = null; state.attemptedReport = null;
    history.replaceState(null, '', projectURL());
    exitReader(false);
    if (state.snapshot) render();
    restoreReportFocus();
  }
  function selectProject(id, writeHistory = true) {
    state.project = id; state.snapshot = null; state.lastSuccess = null; state.error = null; state.filter = 'all'; state.search = ''; state.executor = null; state.report = null; state.attemptedReport = null; state.reportOrigin = null;
    $('executor-dialog').close(); exitReader(false);
    if (writeHistory) history.pushState(null, '', projectURL());
    $('project-title').textContent = state.projects.find(project => String(project.id) === id)?.name || '项目工作台';
    $('project-description').textContent = '正在读取项目…';
    $('breadcrumb-project').textContent = $('project-title').textContent;
    $('content').innerHTML = '<div class="loading-state"><span class="spinner"></span><h2>正在读取项目</h2></div>';
    $('content').setAttribute('aria-busy', 'true');
    renderProjects(); refresh(true);
  }
  function empty(title, description = '') { return `<div class="empty-state"><strong>${escape(title)}</strong>${description ? `<p>${escape(description)}</p>` : ''}</div>`; }
  function notificationHealth() {
    const health = state.snapshot?.notifications;
    const panel = $('service-health');
    panel.hidden = !health || typeof health !== 'object' || Array.isArray(health);
    if (panel.hidden) return;
    // Only the service's successful checks establish health. Browser refreshes
    // and heartbeat timestamps are not proof of a successful notification poll.
    const healthy = !state.error && health.status === 'running' && health.running === true && health.healthy === true && !!health.last_success_at;
    const statusLabels = {starting:'正在启动', checking:'正在检查', running:healthy ? '检查正常' : '等待检查确认', degraded:'检查异常', blocked:'需要处理', stopped:'已停止', stale:'记录已过期', not_running:'未运行'};
    const status = state.error ? '状态待刷新' : statusLabels[health.status] || '状态未知';
    const tone = state.error ? 'unknown' : healthy ? 'completed' : ['degraded','blocked'].includes(health.status) ? 'blocked' : ['starting','checking'].includes(health.status) ? 'waiting' : 'unknown';
    $('notification-status').innerHTML = `<span class="badge ${tone}">${escape(status)}</span>`;
    $('notification-last-check').textContent = health.last_board_success_at ? `看板最近读取成功 ${date(health.last_board_success_at, true)}` : '看板尚无成功读取记录';
    const coordinator = health.coordinator_available === true ? '最近检查可读取' : health.coordinator_available === false ? '最近检查不可读取' : '尚未检查';
    const phases = [['prepared','待提交'],['submitting','提交待确认'],['queued','已入队'],['delivered','已进入会话'],['rejected','被拒绝']];
    const outbox = phases.map(([key,label]) => `<span>${label} <strong>${Number.isSafeInteger(health.outbox?.[key]) && health.outbox[key] >= 0 ? health.outbox[key] : '—'}</strong></span>`).join('');
    $('notification-detail').innerHTML = `<div class="service-health-facts"><span>通知检查成功：${escape(date(health.last_success_at, true))}</span><span>Coordinator：${coordinator}${health.coordinator_checked_at ? ` · ${escape(date(health.coordinator_checked_at, true))}` : ''}</span></div><div class="notification-counts" aria-label="通知投递记录">${outbox}</div><p class="notification-meaning">已入队仅确认队列接收；已进入会话不代表处理或验收完成</p>${health.last_error ? `<p class="notification-error">最近检查问题：${escape(str(health.last_error))}</p>` : ''}<p class="notification-meaning">看板变更与执行完成通知由本地服务负责，关闭页面不会停止服务</p>`;
  }
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
    $('connection').textContent = state.error ? (state.snapshot ? '读取失败 · 保留记录' : '本地读取失败') : state.busy ? '正在读取' : state.lastSuccess ? '本地读取成功' : '等待数据';
    $('last-update').textContent = state.lastSuccess ? `最近读取 ${date(state.lastSuccess, true)} · 每 5 秒刷新` : '本地状态快照 · 每 5 秒刷新';
    notificationHealth();
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
      return `<div class="task-row" role="row"><div role="cell"><div class="task-name">${url ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(task.title || task.id)} ↗</a>` : escape(task.title || task.id)}</div><div class="task-id">${escape(task.id)}${list(task.dependencies).length ? ` · 依赖 ${escape(task.dependencies.join(', '))}` : ''}</div>${reportButtons(taskReports(task))}</div><div role="cell">${badge(task.status)}</div><div class="task-executor" role="cell">${escape(task.assignee || task.executor_id || taskExecutors(task).join(', ') || '未分配')}</div><div class="task-updated" role="cell">${escape(date(task.updated_at))}</div></div>`;
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
    const projectLinks = [['repository_url','GitHub 仓库'],['project_url','GitHub 项目']].map(([key,label]) => { const url = githubURL(project[key]); return url ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${label} ↗</a>` : ''; }).join('');
    $('project-links').innerHTML = projectLinks;
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
      <section class="reports-section" aria-labelledby="reports-title"><div class="section-heading"><h2 id="reports-title">报告与产物 <small>${reports.length}</small></h2><span class="section-caption">HTML 可直接阅读</span></div>${reports.length ? reports.map(report => reportCard(report)).join('') : empty('暂无报告','保存的本地报告会出现在这里')}</section></div>
      <section aria-labelledby="events-title"><div class="section-heading"><h2 id="events-title">最近动态 <small>${events.length}</small></h2><span class="section-caption">基于本地记录</span></div>${events.length ? `<div class="timeline-panel"><ol class="timeline">${events.slice(0,12).map(event => `<li><div class="timeline-message">${escape(event.message || event.title || event.type || '状态更新')}</div><time>${escape(date(event.timestamp || event.updated_at,true))}${event.executor_id ? ` · ${escape(event.executor_id)}` : ''}</time></li>`).join('')}</ol></div>` : empty('暂无动态记录','这里只展示有来源的事件')}</section></div>`;
    $('content').setAttribute('aria-busy','false');
    taskRows();
    if (state.executor && $('executor-dialog').open) renderDrawer(state.executor);
    syncReader();
    notice();
  }
  function renderDrawer(id) {
    const executor = list(state.snapshot?.executors).find(item => String(item.id) === String(id));
    if (!executor) { $('drawer-content').innerHTML = empty('此会话已不在当前快照中','关闭详情后刷新项目'); return; }
    const report = safeURL(executor.report_url, true);
    const linkedReports = taskReports(executor);
    const result = executor.result_summary || executor.result;
    if (!executor.title && !executor.id) return;
    $('drawer-content').innerHTML = `${badge(executor.status)}<h2 id="drawer-title">${escape(executor.title || executor.id)}</h2><dl class="detail-list">${[['执行器',executor.id],['关联任务',executor.task_id],['原生会话',executor.session_id || executor.thread_id],['工作目录',executor.workspace || executor.worktree],['最近更新',date(executor.updated_at,true)],['执行回执状态',executor.executor_status ? (labels[executor.executor_status] || executor.executor_status) : undefined],['回执来源',executor.receipt ? (executor.receipt.status === 'unavailable' ? '回执缺失或不可读取' : executor.receipt.stale ? '缓存记录 · 已过期' : executor.receipt.status === 'ok' ? '本地回执文件' : '回执状态未知') : undefined]].map(([label,value]) => `<div><dt>${label}</dt><dd class="mono">${escape(str(value))}</dd></div>`).join('')}</dl><section class="drawer-section"><h3>路径归属</h3>${list(executor.owned_paths).length ? `<ul class="path-list">${executor.owned_paths.map(path => `<li class="mono">${escape(str(path))}</li>`).join('')}</ul>` : '<p class="muted small">未记录路径归属</p>'}</section><section class="drawer-section"><h3>检查记录</h3>${list(executor.checks).length ? `<ul class="path-list">${executor.checks.map(check => `<li>${typeof check === 'object' ? `${escape(check.name || check.command || '检查')} ${badge(check.status || (check.returncode === 0 || check.passed === true ? 'passed' : check.passed === false || typeof check.returncode === 'number' ? 'failed' : 'unknown'))}` : escape(check)}</li>`).join('')}</ul>` : '<p class="muted small">暂无检查记录；不能据此认定检查通过</p>'}</section><section class="drawer-section"><h3>结果摘要</h3>${result ? `<div class="result-text">${escape(str(result))}</div>` : '<p class="muted small">暂无可展示的结果摘要</p>'}${linkedReports.map(item => reportCard(item)).join('')}${report && !linkedReports.length ? `<a class="report-link" href="${escape(report)}" download>下载本地报告 <span>↓</span></a>` : ''}</section>`;
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
        state.snapshot = null; state.lastSuccess = null; state.error = null; state.executor = null; state.report = null; state.attemptedReport = null; $('executor-dialog').close(); exitReader(false); history.replaceState(null, '', projectURL());
      }
      renderProjects();
      if (!state.project) { state.snapshot = null; state.error = null; state.lastSuccess = new Date().toISOString(); $('content').innerHTML = empty('尚未配置项目','启动工作台时添加项目配置，即可在这里查看任务与执行会话'); $('content').setAttribute('aria-busy','false'); return; }
      const snapshot = await getJSON(`/api/projects/${encodeURIComponent(state.project)}`);
      if (token !== state.request) return;
      if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) throw new Error('无效的数据响应');
      state.snapshot = snapshot; state.error = null; state.lastSuccess = new Date().toISOString();
      const focused = document.activeElement;
      const restore = focused?.id === 'task-search' ? {id:'task-search', selection:[focused.selectionStart,focused.selectionEnd]} : focused?.dataset.filter ? {filter:focused.dataset.filter} : focused?.dataset.report && focused.closest('#content, #drawer-content') ? {report:focused.dataset.report, drawer:!!focused.closest('#drawer-content')} : focused?.dataset.executor ? {executor:focused.dataset.executor} : focused?.tagName === 'A' && focused.closest('#content, #drawer-content') ? {href:focused.href, drawer:!!focused.closest('#drawer-content')} : null;
      render();
      if (restore) {
        const target = restore.id ? $(restore.id) : restore.href ? [...document.querySelectorAll(restore.drawer ? '#drawer-content a' : '#content a')].find(link => link.href === restore.href) : [...document.querySelectorAll(restore.filter ? '[data-filter]' : restore.report ? (restore.drawer ? '#drawer-content [data-report]' : '#content [data-report]') : '[data-executor]')].find(button => restore.filter ? button.dataset.filter === restore.filter : restore.report ? button.dataset.report === restore.report : button.dataset.executor === restore.executor);
        if (target) { target.focus({preventScroll:true}); if (restore.selection) target.setSelectionRange(...restore.selection); }
      }
    } catch (error) {
      if (token !== state.request) return;
      state.error = `无法读取本地项目数据（${error.name === 'AbortError' ? '请求超时' : error.message}）。${state.snapshot ? '保留上次成功读取的记录；稍后会自动重试。' : '请确认本地服务与项目配置可用，稍后会自动重试。'}`;
      if (!state.snapshot) { $('content').innerHTML = empty('项目数据暂时不可用','点击右上角刷新，或等待自动重试'); $('content').setAttribute('aria-busy','false'); }
    } finally { if (token === state.request) { state.busy = false; $('refresh').disabled = false; notice(); } }
  }
  $('projects').addEventListener('click', event => { const button = event.target.closest('[data-project]'); if (!button) return; if (button.dataset.project === state.project) { if (state.report) closeReader(); return; } selectProject(button.dataset.project); });
  $('content').addEventListener('click', event => {
    const filter = event.target.closest('[data-filter]'); if (filter) { state.filter = filter.dataset.filter; taskRows(); }
    const report = event.target.closest('[data-report]'); if (report) { openReport(report.dataset.report); return; }
    const executor = event.target.closest('[data-executor]'); if (executor) { state.executor = executor.dataset.executor; renderDrawer(state.executor); $('executor-dialog').showModal(); }
  });
  $('drawer-content').addEventListener('click', event => { const report = event.target.closest('[data-report]'); if (report) openReport(report.dataset.report, {executor:state.executor}); });
  $('report-reader').addEventListener('click', event => {
    const report = event.target.closest('[data-report]'); if (report) openReport(report.dataset.report);
    if (event.target.closest('#retry-report, #reload-report')) { const selected = currentReport(); if (selected) loadReport(selected); }
  });
  $('close-reader').addEventListener('click', closeReader);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && state.report) { const menu = document.querySelector('.report-history'); if (menu?.open) { menu.open = false; menu.querySelector('summary').focus(); } else closeReader(); } });
  window.addEventListener('popstate', () => {
    const params = new URLSearchParams(location.search);
    const project = params.get('project');
    const report = params.get('report');
    if (project && project !== state.project) { selectProject(project, false); state.report = report; return; }
    const closing = !!state.report && !report;
    state.report = report; state.attemptedReport = null;
    cancelReport();
    if (closing) exitReader(false);
    if (state.snapshot) render();
    if (closing) restoreReportFocus();
  });
  $('content').addEventListener('input', event => { if (event.target.id === 'task-search') { state.search = event.target.value; taskRows(); } });
  $('refresh').addEventListener('click', () => refresh());
  $('close-drawer').addEventListener('click', () => $('executor-dialog').close());
  $('executor-dialog').addEventListener('click', event => { if (event.target === $('executor-dialog')) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
  $('executor-dialog').addEventListener('close', () => { const id = state.executor; state.executor = null; const button = [...document.querySelectorAll('[data-executor]')].find(button => button.dataset.executor === id); if (button) button.focus({preventScroll:true}); });
  try { const theme = localStorage.getItem('delegation-theme'); if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme; } catch {}
  $('theme-toggle').addEventListener('click', () => { const dark = document.documentElement.dataset.theme === 'dark' || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches); document.documentElement.dataset.theme = dark ? 'light' : 'dark'; try { localStorage.setItem('delegation-theme', dark ? 'light' : 'dark'); } catch {} });
  state.project = new URLSearchParams(location.search).get('project');
  state.report = new URLSearchParams(location.search).get('report');
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); },5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();

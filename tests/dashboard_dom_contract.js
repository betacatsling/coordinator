// Deterministic rendering/event contracts with a minimal DOM stub.
// This is deliberately not a browser, a layout test, or proof of CSP enforcement.
const vm = require('vm'), fs = require('fs'), assert = require('assert');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
fixture.detail.tasks[0].title = '<img src=x onerror=alert(1)>';
fixture.details[fixture.detail.project.id] = fixture.detail;
const primary = fixture.detail.project.id;
const reports = fixture.detail.reports;
const report = reports.find(item => item.title === 'SYNTHETIC-TEST.html');
const otherReport = reports.find(item => item.id !== report.id);
const elements = {}, buttons = {};
let serial = 0;
function element(id) {
  return elements[id] ||= {id, innerHTML:'', textContent:'', dataset:{}, listeners:{}, hidden:id === 'report-reader', open:false,
    classList:{add(){}, remove(){}},
    replaceChildren(...children) { this.children = children; for (const child of children) { child.previewBody = fixture.previews[new URL(child.src, location.origin).pathname]; child.listeners?.load?.(); } },
    setAttribute(key, value) { this[key] = value; },
    addEventListener(key, fn) { this.listeners[key] = fn; },
    focus() { document.activeElement = this; }, setSelectionRange(){}, closest(){return null;},
    showModal() { this.open = true; },
    close() { const open = this.open; this.open = false; if (open) this.listeners.close?.(); },
    getBoundingClientRect() { return {left:900, right:1440, top:0, bottom:1000}; }
  };
}
function button(kind, id) {
  return buttons[`${kind}:${id}`] ||= Object.assign(element(`${kind}:${id}`), {dataset:{[kind]:id}, closest:() => element('content')});
}
function query(selector) {
  if (selector.includes('[data-report]')) return reports.map(item => button('report', item.id));
  if (selector.includes('[data-executor]')) return fixture.detail.executors.map(item => button('executor', item.id));
  if (selector === '.filter' || selector.includes('[data-filter]')) return ['all','active','waiting','blocked','completed'].map(id => button('filter', id));
  return [];
}
const document = {getElementById:element, documentElement:{dataset:{}}, querySelectorAll:query, querySelector:() => null,
  createElement:tag => element(`${tag}-${++serial}`), listeners:{}, addEventListener(name, fn){this.listeners[name] = fn;}, activeElement:null};
const window = {listeners:{}, addEventListener(name, fn){this.listeners[name] = fn;}, scrollTo(){}};
const location = {origin:'http://127.0.0.1:18766', search:''};
const historyEntries = [{state:null, url:''}];
let historyIndex = 0;
const history = {
  get state(){return historyEntries[historyIndex].state;},
  replaceState(state, _, url){historyEntries[historyIndex] = {state, url}; location.search = url;},
  pushState(state, _, url){historyEntries.splice(++historyIndex); historyEntries.push({state, url}); location.search = url;},
  back(){if (historyIndex) {location.search = historyEntries[--historyIndex].url; window.listeners.popstate();}},
  forward(){if (historyIndex + 1 < historyEntries.length) {location.search = historyEntries[++historyIndex].url; window.listeners.popstate();}}
};
let fail = false, previewFail = false, wrongType = false, delay = null, pending = null, previewCalls = 0;
const clone = value => JSON.parse(JSON.stringify(value));
const fetch = async (path, options = {}) => {
  const pathname = new URL(path, location.origin).pathname;
  if (pathname.startsWith('/preview/')) {
    previewCalls++;
    assert.equal(options.method, 'HEAD', 'preview preflight retains an independent document CSP');
    if (delay === pathname) return new Promise(resolve => {pending = resolve;});
    return {ok:!previewFail, status:previewFail ? 500 : 200, headers:{get:() => wrongType ? 'application/json' : 'text/html; charset=utf-8'}, text:async() => fixture.previews[pathname]};
  }
  return {ok:!fail, status:fail ? 500 : 200, json:async() => clone(pathname === '/api/projects' ? fixture.catalog : fixture.details[pathname.split('/').pop()])};
};
const context = {window, document, console, location, history, localStorage:{getItem(){return null;}, setItem(){}},
  matchMedia:() => ({matches:false}), URL, URLSearchParams, AbortController, setTimeout, clearTimeout, setInterval(){}, fetch, Intl, Date};
vm.runInNewContext(fs.readFileSync('web/app.js','utf8'), context);
const settle = () => new Promise(resolve => setTimeout(resolve, 10));
const clickData = (container, kind, id) => element(container).listeners.click({target:{closest:selector => selector === `[data-${kind}]` ? button(kind,id) : null}});
const clickID = (container, id) => element(container).listeners.click({target:{closest:selector => selector.split(', ').includes(`#${id}`) ? element(id) : null}});
const refresh = async() => {await element('refresh').listeners.click(); await settle();};
const frame = () => element('report-canvas').children?.[0];
const closeReader = async() => {element('close-reader').listeners.click(); await settle();};
(async() => {
  await settle();
  assert(element('content').innerHTML.includes('executor-card'));
  assert(element('task-rows').innerHTML.includes('&lt;img'));
  assert(!element('task-rows').innerHTML.includes('<img'));
  assert(element('project-links').innerHTML.includes('https://github.com/fixture/test-only'));
  assert.equal(element('connection').textContent, '本地读取成功');
  assert(element('last-update').textContent.includes('最近读取'));
  fixture.detail.notifications = {status:'running', running:true, healthy:true,
    last_success_at:'2026-10-05T10:00:00Z', last_board_success_at:'2026-10-05T09:59:58Z',
    coordinator_available:true, coordinator_checked_at:'2026-10-05T09:59:59Z',
    outbox:{prepared:1, submitting:2, queued:3, delivered:4, rejected:0}, last_error:null};
  await refresh();
  assert(!element('service-health').hidden);
  assert(!element('service-health').open, 'notification details are collapsed initially');
  assert(element('notification-status').innerHTML.includes('检查正常'));
  assert(element('notification-last-check').textContent.includes('看板最近读取成功'));
  assert(element('notification-detail').innerHTML.includes('已入队 <strong>3</strong>'));
  assert(element('notification-detail').innerHTML.includes('已进入会话 <strong>4</strong>'));
  assert(element('notification-detail').innerHTML.includes('不代表处理或验收完成'));
  assert(element('notification-detail').innerHTML.includes('关闭页面不会停止服务'));
  element('service-health').open = true;
  await refresh();
  assert(element('service-health').open, 'polling preserves expanded service details');
  for (const [status,label] of Object.entries({starting:'正在启动', checking:'正在检查', degraded:'检查异常', blocked:'需要处理', stopped:'已停止', stale:'记录已过期', not_running:'未运行', unexpected:'状态未知'})) {
    fixture.detail.notifications.status = status;
    await refresh();
    assert(element('notification-status').innerHTML.includes(label), status);
    assert(!element('notification-status').innerHTML.includes('completed'), 'non-running service cannot appear healthy');
  }
  fixture.detail.notifications.status = 'running';
  fixture.detail.notifications.last_success_at = null;
  fixture.detail.notifications.last_board_success_at = null;
  await refresh();
  assert(!element('notification-status').innerHTML.includes('检查正常'), 'heartbeat/running alone is not a successful poll');
  assert(element('notification-last-check').textContent.includes('尚无成功读取记录'));
  fixture.detail.notifications.last_success_at = '2026-10-05T10:00:00Z';
  fixture.detail.notifications.running = false;
  await refresh();
  assert(!element('notification-status').innerHTML.includes('检查正常'), 'a saved success alone is not current health');
  fixture.detail.notifications.running = true;
  fixture.detail.notifications.healthy = false;
  fixture.detail.notifications.last_error = '<img src=x onerror=alert(1)>';
  await refresh();
  assert(!element('notification-status').innerHTML.includes('检查正常'));
  assert(element('notification-detail').innerHTML.includes('&lt;img'));
  assert(!element('notification-detail').innerHTML.includes('<img'));
  fixture.detail.notifications.healthy = true;
  fixture.detail.notifications.last_error = null;
  fixture.detail.notifications.last_board_success_at = '2026-10-05T09:59:58Z';
  await refresh();
  for (const [filter,count] of Object.entries({active:1, waiting:1, blocked:1, completed:2, all:5})) {
    clickData('content', 'filter', filter);
    assert.equal((element('task-rows').innerHTML.match(/class="task-row"/g) || []).length, count, filter);
  }
  element('content').listeners.input({target:{id:'task-search',value:'fixture-job-0'}});
  assert.equal((element('task-rows').innerHTML.match(/class="task-row"/g) || []).length, 1);
  assert(element('task-rows').innerHTML.includes(`data-report="${report.id}"`), 'task has exact associated report');
  clickData('content', 'executor', 'fixture-job-0');
  assert(element('executor-dialog').open);
  assert(element('drawer-content').innerHTML.includes('通过'));
  assert(element('drawer-content').innerHTML.includes('synthetic-session-0'));
  clickData('drawer-content', 'report', report.id);
  await settle();
  assert(!element('executor-dialog').open, 'reader replaces the drawer');
  assert(!element('report-reader').hidden && element('overview').hidden);
  assert.equal(document.activeElement.id, 'reader-title');
  assert.equal(frame().sandbox, '');
  assert.equal(frame().src, location.origin + report.preview_url);
  assert(!('srcdoc' in frame()), 'srcdoc would inherit the dashboard inline-style block');
  assert.equal(frame().referrerpolicy, 'no-referrer');
  assert(frame().previewBody.includes('Synthetic QA artifact'));
  assert(frame().previewBody.includes('Content-Security-Policy'));
  assert(!frame().previewBody.includes('<script>'));
  assert(element('reader-actions').innerHTML.includes('https://github.com/fixture/test-only/issues/1'));
  assert(element('reader-actions').innerHTML.includes('download'));
  assert(location.search.includes(`report=${report.id}`));
  const retainedFrame = frame(), calls = previewCalls;
  await refresh();
  assert.strictEqual(frame(), retainedFrame, 'polling preserves reading position and frame');
  assert.equal(previewCalls, calls, 'polling does not refetch report');
  report.size++;
  await refresh();
  assert(!element('reader-update').hidden && frame() === retainedFrame);
  clickID('report-reader', 'reload-report');
  await settle();
  assert.notStrictEqual(frame(), retainedFrame);
  assert(element('reader-update').hidden);
  await closeReader();
  assert(element('report-reader').hidden && !element('overview').hidden);
  assert.equal(document.activeElement.dataset.executor, 'fixture-job-0');
  history.forward(); await settle();
  assert(frame().previewBody.includes('Synthetic QA artifact'));
  clickData('report-reader', 'report', otherReport.id); await settle();
  assert(frame().previewBody.includes('Older synthetic report'));
  assert(element('reader-actions').innerHTML.includes('GitHub 仓库'));
  assert(!element('reader-actions').innerHTML.includes('GitHub 任务'));
  assert(element('reader-heading').innerHTML.includes('不代表同一报告的版本历史'));
  await closeReader();
  previewFail = true;
  clickData('content', 'report', report.id); await settle();
  assert(element('reader-status').innerHTML.includes('HTTP 500'));
  assert(!frame());
  previewFail = false;
  clickID('report-reader', 'retry-report'); await settle();
  assert(frame());
  fixture.detail.reports = reports.filter(item => item.id !== report.id);
  await refresh();
  assert(!frame() && element('reader-status').innerHTML.includes('找不到这份报告'));
  fixture.detail.reports = reports;
  await refresh();
  assert(frame(), 'restored file can be opened without leaving the reader');
  await closeReader();
  wrongType = true;
  clickData('content', 'report', report.id); await settle();
  assert(!frame() && element('reader-status').innerHTML.includes('报告格式不正确'));
  wrongType = false;
  await closeReader();
  delay = report.preview_url;
  clickData('content', 'report', report.id); await settle();
  assert(pending, 'first report request is delayed');
  clickData('report-reader', 'report', otherReport.id); await settle();
  pending({ok:true, headers:{get:() => 'text/html'}, text:async() => '<h1>Stale report must never render</h1>'});
  await settle();
  assert(frame().previewBody.includes('Older synthetic report'), 'out-of-order response cannot replace the current report');
  await closeReader();
  pending = null;
  clickData('content', 'report', report.id); await settle();
  clickData('projects', 'project', fixture.catalog.projects[1].id); await settle();
  pending({ok:true, headers:{get:() => 'text/html'}, text:async() => '<h1>Stale project must never render</h1>'});
  await settle();
  assert(element('report-reader').hidden && !frame(), 'project navigation discards pending previews');
  assert(!location.search.includes('report='));
  assert(element('project-title').textContent.includes('Empty'));
  delay = null;
  clickData('projects', 'project', primary); await settle();
  history.replaceState(null, '', `?project=${primary}&report=missing`);
  window.listeners.popstate(); await settle();
  assert(!frame() && element('reader-status').innerHTML.includes('找不到这份报告'));
  await closeReader();
  assert.equal(document.activeElement.id, 'project-title', 'invalid deep link closes to a useful focus target');
  element('theme-toggle').listeners.click();
  assert.equal(document.documentElement.dataset.theme, 'dark');
  fail = true;
  const lastRead = element('last-update').textContent;
  await refresh();
  assert(element('notice').innerHTML.includes('HTTP 500'));
  assert(element('content').innerHTML.includes('executor-card'));
  assert.equal(element('connection').textContent, '读取失败 · 保留记录');
  assert.equal(element('last-update').textContent, lastRead, 'failed reads never advance the successful-read timestamp');
  assert(element('notification-status').innerHTML.includes('状态待刷新'));
  assert(!element('notification-status').innerHTML.includes('检查正常'), 'cached service health is not current after HTTP failure');
  fail = false;
  await refresh();
  assert.equal(element('connection').textContent, '本地读取成功');
  assert(element('notification-status').innerHTML.includes('检查正常'));
  delete fixture.detail.notifications;
  await refresh();
  assert(element('service-health').hidden, 'absent notification evidence does not invent a service status');
  console.log('PASS deterministic frontend contracts: escaping, filters/search, exact report associations, safe frame configuration, GitHub links, downloads, reader/drawer navigation, focus, history, polling stability, update/reload, errors/retry, removed/restored reports, MIME validation, request races, project changes, successful/failed local reads, collapsed notification health, poll evidence, queued versus observed-in-session notices and stale-health recovery. Not visual browser QA or CSP execution testing.');
})().catch(error => {console.error(error); process.exitCode = 1;});

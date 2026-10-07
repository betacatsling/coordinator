// Coordinator Console — dependency-free client for console/server.mjs.
const $ = (s, el = document) => el.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const STAGES = [['ready', 'Ready'], ['inProgress', 'In progress'], ['inReview', 'In review'], ['done', 'Done']];
const icon = {
  chat: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 18.5V6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v7a2.5 2.5 0 0 1-2.5 2.5H9Z"/></svg>',
  ext: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/></svg>',
  close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
  alert: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8.5v4.5M12 16.5v.01"/><circle cx="12" cy="12" r="9"/></svg>',
  shield: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4.5 6v5.5c0 4.6 3.1 8.2 7.5 9.5 4.4-1.3 7.5-4.9 7.5-9.5V6Z"/></svg>',
  chev: '<svg viewBox="0 0 24 24" aria-hidden="true" class="chev"><path d="m9 6 6 6-6 6"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.6-4.5M4 5v4h4M4 13a8 8 0 0 0 14.6 4.5M20 19v-4h-4"/></svg>',
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10-6.5Z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8.5 5.5v13M15.5 5.5v13"/></svg>',
  spark: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/></svg>',
  inbox: '<svg viewBox="0 0 24 24" aria-hidden="true" class="glyph"><path d="M3.5 13.5 6 5.5h12l2.5 8M3.5 13.5V18a1.5 1.5 0 0 0 1.5 1.5h14a1.5 1.5 0 0 0 1.5-1.5v-4.5M3.5 13.5h5l1 2h5l1-2h5"/></svg>',
  broken: '<svg viewBox="0 0 24 24" aria-hidden="true" class="glyph"><circle cx="12" cy="12" r="9"/><path d="M8 8l8 8"/></svg>',
};

const store = { meta: null, project: null, notices: null, issue: null, error: null, loading: true };
const api = async (path, body) => {
  const res = await fetch(path, body ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) } : {});
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok) throw Object.assign(new Error(data.error ?? `HTTP ${res.status}`), { status: res.status });
  return data;
};

// ——— helpers ———
const hue = s => { let h = 0; for (const ch of String(s)) h = (h * 31 + ch.charCodeAt(0)) % 360; return `hsl(${h} 45% 55%)`; };
const avatar = login => `<span class="avatar" style="--h:${hue(login ?? '?')}" aria-hidden="true">${esc((login ?? '?').slice(0, 1))}</span>`;
const stageOf = statusId => Object.entries(store.meta.config.statusField.options).find(([, o]) => o.id === statusId)?.[0] ?? null;
const stageLabel = k => STAGES.find(([s]) => s === k)?.[1] ?? 'No status';
const dot = (stage, ring = false) => `<span class="dot${ring ? ' ring' : ''}" style="--c:var(--s-${stage ?? 'unset'})" aria-hidden="true"></span>`;
const shortRev = r => r ? r.slice(0, 7) : '—';
const ago = iso => { const s = Math.round((Date.now() - new Date(iso)) / 1000);
  return s < 10 ? 'just now' : s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); };
const authorized = login => store.meta.config.authorizedUsers.includes(String(login ?? '').toLowerCase());
const stripMarkers = body => String(body ?? '').replace(/<!--\s*pi-project-github:[^>]*-->/g, '').trim();

// Minimal, escape-first Markdown: paragraphs, lists, code, emphasis, links.
function md(src) {
  const text = stripMarkers(src); if (!text) return '<p class="thread-empty">No description.</p>';
  const inline = s => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  const out = []; const blocks = text.split(/```/);
  blocks.forEach((block, i) => {
    if (i % 2) { out.push(`<pre><code>${esc(block.replace(/^\w*\n/, ''))}</code></pre>`); return; }
    for (const para of block.split(/\n{2,}/)) {
      const lines = para.split('\n').filter(l => l.trim()); if (!lines.length) continue;
      if (lines.every(l => /^\s*[-*]\s+/.test(l))) out.push(`<ul>${lines.map(l => `<li>${inline(l.replace(/^\s*[-*]\s+/, ''))}</li>`).join('')}</ul>`);
      else if (lines.every(l => /^\s*\d+\.\s+/.test(l))) out.push(`<ol>${lines.map(l => `<li>${inline(l.replace(/^\s*\d+\.\s+/, ''))}</li>`).join('')}</ol>`);
      else if (/^#{1,3}\s/.test(lines[0])) out.push(`<h3>${inline(lines[0].replace(/^#+\s/, ''))}</h3>${lines.length > 1 ? `<p>${lines.slice(1).map(inline).join('<br>')}</p>` : ''}`);
      else if (lines.every(l => l.startsWith('>'))) out.push(`<blockquote>${lines.map(l => inline(l.replace(/^>\s?/, ''))).join('<br>')}</blockquote>`);
      else out.push(`<p>${lines.map(inline).join('<br>')}</p>`);
    }
  });
  return out.join('');
}

function toast(message, kind = '') {
  const el = document.createElement('div'); el.className = `toast ${kind}`; el.textContent = message;
  $('#toasts').append(el); setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 220); }, kind === 'err' ? 5200 : 2600);
}

// ——— chrome ———
function renderChrome() {
  const { meta, project } = store; const w = project?.watch ?? store.notices?.watch;
  if (meta) $('#scope-crumb').innerHTML = `${meta.mode === 'demo' ? '<span class="mode-tag" title="In-memory GitHub; nothing leaves this machine">Demo</span>' : ''}
    <b class="ellipsis">${esc(meta.config.repository)}</b><span class="sep">/</span><span class="ellipsis">${esc(project?.title ?? meta.config.projectId)}</span>`;
  const pill = $('#watch-pill');
  const state = store.error ? ['err', 'Unreachable', 'GitHub unreachable'] : !w ? ['', '…', 'Connecting'] : w.active ? ['on', 'Watching', `Watching every ${Math.round(w.pollIntervalMs / 1000)}s`] : w.paused ? ['paused', 'Paused', 'Watcher paused'] : ['', 'Idle', 'Watcher idle'];
  pill.innerHTML = `<span class="pulse ${state[0]}"></span><span class="label-long">${esc(state[2])}</span><span class="sr">${esc(state[1])}</span>`;
  pill.setAttribute('aria-label', `${state[2]} — open notices`);
  const badge = $('#notice-badge'); const n = w?.pendingChanges ?? 0;
  badge.hidden = !n; badge.textContent = n; badge.setAttribute('aria-label', `${n} pending`);
  for (const a of document.querySelectorAll('.rail a')) {
    if (a.dataset.view === route().view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
}

// ——— routing ———
const route = () => { const [, view = 'board', id] = location.hash.split('/'); return { view: ['board', 'notices', 'scope'].includes(view) ? view : 'board', id: id && decodeURIComponent(id) }; };

// ——— board ———
function boardSkeleton() {
  return `<section class="view"><div class="page-head"><div><p class="eyebrow">Project board</p><div class="sk" style="width:320px;height:40px"></div></div></div>
    <div class="board" style="--cols:4">${[3, 2, 2, 1].map(n => `<div class="column"><div class="col-head"><div class="sk" style="width:90px;height:14px"></div></div>
    <div class="cards">${Array.from({ length: n }, () => '<div class="sk" style="height:92px"></div>').join('')}</div></div>`).join('')}</div></section>`;
}
function errorState(err) {
  return `<section class="view state">${icon.broken}<h2>The board is out of reach</h2>
    <p>Coordinator fails closed: when the scoped GitHub read is incomplete or a mapping drifts, nothing is shown rather than something partial.</p>
    <pre>${esc(err.message)}</pre><button class="btn" data-act="reload">${icon.refresh}Try again</button></section>`;
}
function renderBoard() {
  const { project, meta, notices } = store;
  if (store.error && !project) return errorState(store.error);
  if (!project || !meta) return boardSkeleton();
  const changed = new Set([...(notices?.pending?.changes ?? []), ...(notices?.delivery?.changes ?? [])].filter(c => c.kind !== 'current').map(c => c.issueId));
  const cols = STAGES.filter(([k]) => meta.config.statusField.options[k]).map(([k]) => ({ key: k, name: meta.config.statusField.options[k].name, issues: [] }));
  const unset = { key: null, name: 'No status', issues: [] };
  for (const issue of project.issues) (cols.find(c => c.key === stageOf(issue.statusId)) ?? unset).issues.push(issue);
  if (unset.issues.length) cols.unshift(unset);
  const total = project.issues.length; const done = cols.find(c => c.key === 'done')?.issues.length ?? 0;
  const active = (cols.find(c => c.key === 'inProgress')?.issues.length ?? 0) + (cols.find(c => c.key === 'inReview')?.issues.length ?? 0);
  const { id } = route(); let i = 0;
  const card = issue => `<button class="card" style="--i:${i++}" data-issue="${esc(issue.id)}" ${issue.id === id ? 'aria-current="true"' : ''}>
      <span class="card-title">${esc(issue.title)}</span>
      <span class="card-meta"><span class="num">#${issue.number}</span>${avatar(issue.author)}<span>${esc(issue.author ?? 'unknown')}</span><span class="spacer"></span>
      ${changed.has(issue.id) ? '<span class="changed" title="Changed since last acknowledged notice"></span><span class="sr">changed</span>' : ''}
      ${issue.state !== 'OPEN' ? `<span class="tag">${esc(issue.state.toLowerCase())}</span>` : ''}</span></button>`;
  return `<section class="view">
    <div class="page-head"><div><p class="eyebrow">Project board</p><h1 class="title">${esc(project.title)}</h1>
      <p class="lede">Every Issue from <span class="mono">${esc(meta.config.repository)}</span> on this Project, across all statuses. Open a card to read it in full before writing.</p></div>
      <div class="head-aside">${meta.mode === 'demo' ? `<button class="btn ghost" data-act="simulate" title="Add a comment from someone else on GitHub">${icon.spark}Simulate activity</button>` : ''}
      <a class="btn" href="${esc(project.url)}" target="_blank" rel="noopener noreferrer">${icon.ext}Open on GitHub</a></div></div>
    <ul class="stats"><li><b>${total}</b><span>Issues</span></li><li><b>${active}</b><span>Active</span></li><li><b>${done}</b><span>Done</span></li>
      <li><b>${changed.size}</b><span>Changed</span></li></ul>
    ${total ? `<div class="board" style="--cols:${cols.length}">${cols.map(c => `<section class="column" aria-label="${esc(c.name)}">
      <header class="col-head">${dot(c.key, c.key === null)}<h2>${esc(c.name)}</h2><span class="count">${c.issues.length}</span></header>
      <div class="cards">${c.issues.length ? c.issues.map(card).join('') : '<div class="col-empty">Nothing here</div>'}</div></section>`).join('')}</div>`
    : `<div class="state">${icon.inbox}<h2>An empty board</h2><p>No Issues from ${esc(meta.config.repository)} are on this Project yet. Add one on GitHub and it will appear on the next poll.</p></div>`}
  </section>`;
}

// ——— issue drawer ———
let lastFocus = null;
function openDrawer(id) {
  const drawer = $('#drawer'), scrim = $('#scrim');
  if (drawer.hidden) { lastFocus = document.activeElement; drawer.hidden = false; scrim.hidden = false; drawer.classList.remove('out'); scrim.classList.remove('out'); document.body.style.overflow = 'hidden'; }
  if (store.issue?.id !== id) { store.issue = null; renderDrawer(); }
  loadIssue(id);
}
function closeDrawer() {
  const drawer = $('#drawer'), scrim = $('#scrim'); if (drawer.hidden) return;
  drawer.classList.add('out'); scrim.classList.add('out'); document.body.style.overflow = '';
  setTimeout(() => { drawer.hidden = true; scrim.hidden = true; drawer.innerHTML = ''; }, 200);
  store.issue = null; lastFocus?.focus?.();
}
async function loadIssue(id) {
  try { store.issueError = null; const issue = await api(`/api/issues/${encodeURIComponent(id)}`); if (route().id !== id) return; store.issue = { ...issue, readAt: new Date().toISOString() }; }
  catch (e) { store.issueError = e; }
  renderDrawer();
}
function renderDrawer() {
  const drawer = $('#drawer'); if (drawer.hidden) return;
  const issue = store.issue; const draft = $('#composer-text')?.value ?? '';
  const focusedComposer = document.activeElement?.id === 'composer-text';
  if (store.issueError) {
    drawer.innerHTML = `<div class="d-head"><div class="d-top"><span>Issue</span><button class="icon-btn" data-act="close" aria-label="Close">${icon.close}</button></div></div>
      <div class="d-body"><div class="state" style="margin-top:8vh">${icon.broken}<h2 id="drawer-title">Can’t read this Issue</h2><p>${esc(store.issueError.message)}</p>
      <button class="btn" data-act="reread">${icon.refresh}Read again</button></div></div>`; return;
  }
  if (!issue) {
    drawer.innerHTML = `<div class="d-head"><div class="d-top"><div class="sk" style="width:120px;height:14px"></div><button class="icon-btn" data-act="close" aria-label="Close">${icon.close}</button></div>
      <h2 class="sr" id="drawer-title">Loading Issue</h2><div class="sk" style="height:34px;width:80%;margin-bottom:16px"></div><div class="sk" style="height:14px;width:50%"></div></div>
      <div class="d-body"><div class="sk" style="height:40px;margin-bottom:32px"></div>${[90, 70, 80].map(w => `<div class="sk" style="height:14px;width:${w}%;margin-bottom:10px"></div>`).join('')}</div>`;
    drawer.focus({ preventScroll: true }); return;
  }
  const opts = store.meta.config.statusField.options; const stage = stageOf(issue.statusId);
  const stages = STAGES.filter(([k]) => opts[k]);
  const own = new Set(issue.ownCommentIds ?? []);
  const comments = issue.comments.map(c => `<li class="comment">${avatar(c.author)}<div>
      <div class="c-head"><b>${esc(c.author ?? 'unknown')}</b>
      ${own.has(c.id) ? `<span class="tag self">Manager</span>` : c.authorAuthorized ? `<span class="tag ok">${icon.check}authorized</span>` : `<span class="tag" title="Not in authorizedUsers — provenance only">external</span>`}
      <span class="c-id">${esc(c.id)}</span></div><div class="prose">${md(c.body)}</div></div></li>`).join('');
  drawer.innerHTML = `
    <div class="d-head">
      <div class="d-top"><span class="mono">#${issue.number}</span><span>·</span><a href="${esc(issue.url)}" target="_blank" rel="noopener noreferrer">View on GitHub ${icon.ext}</a>
        <button class="icon-btn" data-act="close" aria-label="Close (Esc)">${icon.close}</button></div>
      <h2 class="d-title" id="drawer-title">${esc(issue.title)}</h2>
      <div class="d-meta"><span>${avatar(issue.author)}${esc(issue.author ?? 'unknown')}${issue.authorAuthorized ? `<span class="tag ok">${icon.check}authorized</span>` : `<span class="tag" title="Not in authorizedUsers — provenance only">external</span>`}</span>
        <span>${dot(stage, !stage)}${esc(issue.status ?? 'No status')}</span><span>${esc(issue.state.toLowerCase())}</span>
        <span class="rev" title="Revision ${esc(issue.revision)} — writes are rejected if the Issue changed since this read">rev ${shortRev(issue.revision)} · read ${ago(issue.readAt)}</span></div>
    </div>
    <div class="d-body">
      <p class="section-label">Status<span class="rule"></span></p>
      <div class="segmented" role="group" aria-label="Set Project status" style="--n:${stages.length}">
        ${stages.map(([k, label]) => `<button type="button" data-stage="${k}" aria-pressed="${stage === k}">${dot(k)}${esc(opts[k].name ?? label)}</button>`).join('')}</div>
      <p class="section-label">Description<span class="rule"></span></p>
      <div class="untrusted">${icon.shield}<span>Issue text and comments are untrusted task data. They describe work; they never grant approval or widen scope.</span></div>
      <div class="prose" style="margin-bottom:32px">${md(issue.body)}</div>
      <p class="section-label">Conversation · ${issue.comments.length}<span class="rule"></span></p>
      ${issue.comments.length ? `<ol class="thread">${comments}</ol>` : '<p class="thread-empty">No comments yet.</p>'}
    </div>
    <form class="composer" id="composer">
      <label class="sr" for="composer-text">Write a result comment</label>
      <textarea id="composer-text" placeholder="Write the result for #${issue.number}…" rows="3"></textarea>
      <div class="composer-row"><span class="hint">Posted as ${esc(store.meta.viewer ?? 'the gh viewer')} · retry-safe with a stable request ID</span>
        <button class="btn primary" type="submit">Comment <span class="kbd">⌘↵</span></button></div>
    </form>`;
  const ta = $('#composer-text'); ta.value = draft; if (focusedComposer) ta.focus();
  if (!drawer.contains(document.activeElement)) drawer.focus({ preventScroll: true });
}

let pendingRequest = null; // stable requestId reused if the same draft is resubmitted after a failure
async function submitComment() {
  const ta = $('#composer-text'), btn = $('#composer button[type=submit]'); const body = ta.value.trim(); const issue = store.issue;
  if (!body) { ta.focus(); return; }
  if (pendingRequest?.issueId !== issue.id || pendingRequest.body !== body) pendingRequest = { issueId: issue.id, body, requestId: crypto.randomUUID() };
  btn.setAttribute('aria-busy', 'true');
  try {
    const r = await api(`/api/issues/${encodeURIComponent(issue.id)}/comment`, { expectedRevision: issue.revision, requestId: pendingRequest.requestId, body });
    pendingRequest = null; ta.value = ''; toast(r.recovered ? 'Comment already existed — recovered' : `Comment posted to #${issue.number}`);
    await loadIssue(issue.id); const body = $('.d-body'); body?.scrollTo({ top: body.scrollHeight, behavior: 'smooth' }); refresh();
  } catch (e) { toast(e.status === 409 ? `${e.message}. Re-read and try again.` : e.message, 'err'); if (e.status === 409) await loadIssue(issue.id); }
  finally { $('#composer button[type=submit]')?.removeAttribute('aria-busy'); }
}
async function setStage(stageKey, btn) {
  const issue = store.issue; if (!issue || stageOf(issue.statusId) === stageKey) return;
  for (const b of document.querySelectorAll('.segmented button')) b.setAttribute('aria-pressed', b === btn);
  btn.setAttribute('aria-busy', 'true');
  try {
    await api(`/api/issues/${encodeURIComponent(issue.id)}/status`, { expectedRevision: issue.revision, expectedStatusId: issue.statusId, stage: stageKey });
    toast(`#${issue.number} → ${store.meta.config.statusField.options[stageKey].name}`);
  } catch (e) { toast(e.message, 'err'); }
  await loadIssue(issue.id); refresh();
}

// ——— notices ———
function renderNotices() {
  const n = store.notices; if (!n) return `<section class="view"><div class="page-head"><div><p class="eyebrow">Watcher</p><div class="sk" style="width:280px;height:40px"></div></div></div><div class="sk" style="height:320px;border-radius:14px"></div></section>`;
  const w = n.watch; const queued = [...(n.delivery ? [{ ...n.delivery, phase: 'Awaiting receipt' }] : []), ...(n.pending ? [{ ...n.pending, phase: 'Queued' }] : [])];
  const change = c => `<div class="change"><div class="change-head"><span class="mono" style="color:var(--muted)">#${c.number}</span>
      <a href="#/board/${encodeURIComponent(c.issueId)}">${esc(c.title)}</a><span class="tag kind">${esc(c.kind)}</span></div>
      <ul class="events">${(c.events ?? []).map(e => `<li><div><span class="ev-kind">${esc(e.kind)}</span>${e.author ? ` · @${esc(e.author)}` : ''}${e.from ? ` · ${esc(e.from)} → ${esc(e.to)}` : ''}
      ${e.body ? `<q>${esc(stripMarkers(e.body))}</q>` : ''}</div></li>`).join('')}</ul></div>`;
  return `<section class="view">
    <div class="page-head"><div><p class="eyebrow">Watcher</p><h1 class="title">Notices <em>for the Manager</em></h1>
      <p class="lede">Changes observed between polls are batched into a single notice. A batch stays open until the Manager session records its receipt.</p></div>
      <div class="head-aside">${w.active ? `<button class="btn" data-watch="stop">${icon.pause}Pause watcher</button>` : `<button class="btn primary" data-watch="start">${icon.play}Start watcher</button>`}</div></div>
    <div class="panel" style="margin-bottom:32px"><dl class="watch-grid" style="margin:0">
      <div><dt>State</dt><dd><span class="pulse ${w.active ? 'on' : w.paused ? 'paused' : ''}"></span>${w.active ? 'Watching' : w.paused ? 'Paused' : 'Idle'}</dd></div>
      <div><dt>Interval</dt><dd>${Math.round(w.pollIntervalMs / 1000)}<span style="font:400 13px var(--sans);color:var(--muted)">seconds</span></dd></div>
      <div><dt>Open changes</dt><dd>${w.pendingChanges}<span style="font:400 13px var(--sans);color:var(--muted)">${w.awaitingReceipt ? 'awaiting receipt' : 'issues'}</span></dd></div></dl></div>
    <div class="split">
      <div><div class="panel"><div class="panel-head"><h3>Open batches</h3><span class="sub">${queued.length ? `${queued.reduce((a, q) => a + q.changes.length, 0)} issue(s)` : ''}</span></div>
        ${queued.length ? queued.map(q => `<div class="panel-head" style="background:var(--bg-2)"><span class="tag">${esc(q.phase)}</span><span class="sub mono">${esc(q.id.slice(0, 8))}</span>
          ${q.reason ? `<span class="sub">${q.reason === 'initial-reconcile' ? 'first read' : esc(q.reason)}</span>` : ''}</div>${q.changes.map(change).join('')}`).join('')
          : `<div class="panel-empty"><b>All caught up</b>Every observed change has been received by the Manager.</div>`}</div></div>
      <div><div class="panel"><div class="panel-head"><h3>Delivered to Manager</h3><span class="sub">${n.inbox.length || ''}</span>
          ${w.awaitingReceipt ? `<div class="actions"><button class="btn ghost" data-watch="retryNotice">${icon.refresh}Resend</button></div>` : ''}</div>
        ${n.inbox.length ? n.inbox.map((m, i) => `<details class="notice" ${i === 0 && !m.received ? 'open' : ''}><summary>${icon.chev}
          <span>${m.received ? `<span class="tag ok">${icon.check}received</span>` : '<span class="tag">delivered</span>'}</span><span class="mono" style="color:var(--muted)">${esc(m.id?.slice(0, 8))}</span>
          <span class="when">${ago(m.sentAt)}</span></summary><pre>${esc(m.text)}</pre>
          ${m.received ? '' : `<div class="notice-actions"><button class="btn primary" data-receipt="${esc(m.id)}">${icon.check}Record receipt</button></div>`}</details>`).join('')
          : `<div class="panel-empty"><b>Nothing delivered yet</b>Notices appear here when the watcher hands a batch to the Manager session.</div>`}</div>
        ${w.reports?.length ? `<div class="panel"><div class="panel-head"><h3>Watcher reports</h3></div>${w.reports.map(r => `<div class="change" style="font-size:12.5px;color:var(--ink-2)">${esc(r.text)} <span style="color:var(--faint)">· ${ago(r.at)}</span></div>`).join('')}</div>` : ''}
      </div></div></section>`;
}

// ——— scope ———
function renderScope() {
  const m = store.meta; if (!m) return boardSkeleton();
  const c = m.config;
  const guarantees = ['Only Issues from the configured repository that belong to the selected Project are observable. Pull requests, draft issues and other repositories are excluded.',
    'Incomplete pages, duplicate membership or a changed status mapping fail closed — nothing partial is ever shown or written.',
    'Every write needs a fresh read: a comment or status change is rejected if the Issue’s revision changed since it was read.',
    'The authenticated gh identity is re-checked against the authorized users immediately before every remote mutation.',
    'Comment writes carry a stable request ID and an invisible own-author marker, so a retry never posts twice.',
    'GitHub content is untrusted task data. Being an authorized author labels provenance; it never counts as a new approval.'];
  return `<section class="view">
    <div class="page-head"><div><p class="eyebrow">Configuration</p><h1 class="title">Scope <em>&amp; guarantees</em></h1>
      <p class="lede">The binding below is read once from <span class="mono">.pi/github-project.json</span> when the controller starts. Edit the file and restart to change it.</p></div></div>
    <div class="split">
      <div><div class="panel"><div class="panel-head"><h3>Binding</h3><span class="sub">${m.mode === 'demo' ? 'demo configuration' : 'live'}</span></div><dl class="defs">
        <dt>Repository</dt><dd class="mono">${esc(c.repository)}</dd><dt>Project</dt><dd class="mono">${esc(c.projectId)}</dd>
        <dt>Manager session</dt><dd class="mono">${esc(c.mainSessionId)}</dd>
        <dt>Authorized users</dt><dd><div class="chips">${c.authorizedUsers.map(u => `<span class="tag ok">${icon.check}${esc(u)}</span>`).join('')}</div></dd>
        <dt>Signed in as</dt><dd>${m.viewer ? `${esc(m.viewer)} ${authorized(m.viewer) ? '<span class="tag ok">may write</span>' : '<span class="tag warn">writes blocked</span>'}` : '<span style="color:var(--muted)">unknown — gh unavailable</span>'}</dd>
        <dt>Poll interval</dt><dd>${c.pollIntervalMs / 1000} s</dd></dl></div>
        <div class="panel"><div class="panel-head"><h3>Status mapping</h3><span class="sub mono">${esc(c.statusField.name)} · ${esc(c.statusField.id)}</span></div>
          <table class="map"><thead><tr><th>Stage</th><th>Option</th><th>ID</th></tr></thead><tbody>
          ${STAGES.filter(([k]) => c.statusField.options[k]).map(([k]) => `<tr><td><span style="display:inline-flex;align-items:center;gap:8px">${dot(k)}<span class="mono">${k}</span></span></td><td>${esc(c.statusField.options[k].name)}</td><td><span class="mono">${esc(c.statusField.options[k].id)}</span></td></tr>`).join('')}
          </tbody></table></div></div>
      <div><div class="panel"><div class="panel-head"><h3>What this console guarantees</h3></div><ol class="guarantees">${guarantees.map(g => `<li>${g}</li>`).join('')}</ol></div></div>
    </div></section>`;
}

// ——— render loop ———
let lastView = null;
function render() {
  const { view, id } = route(); const main = $('#main');
  const html = view === 'notices' ? renderNotices() : view === 'scope' ? renderScope() : renderBoard();
  const scrollY = window.scrollY; const boardScroll = $('.board')?.scrollLeft; const openNotices = [...document.querySelectorAll('details.notice')].map(d => d.open);
  main.innerHTML = html;
  if (view === lastView) { for (const el of main.querySelectorAll('.view, .card, .comment')) el.style.animation = 'none'; window.scrollTo(0, scrollY);
    if (boardScroll && $('.board')) $('.board').scrollLeft = boardScroll; document.querySelectorAll('details.notice').forEach((d, i) => { if (openNotices[i] !== undefined) d.open = openNotices[i]; }); }
  lastView = view;
  renderChrome();
  if (view === 'board' && id) openDrawer(id); else closeDrawer();
}

async function refresh() {
  try {
    const [project, notices] = await Promise.all([api('/api/project'), api('/api/notices')]);
    store.project = project; store.notices = notices; store.error = null;
  } catch (e) { store.error = e; store.notices ??= await api('/api/notices').catch(() => null); }
  const drawerOpen = !$('#drawer').hidden; const { view, id } = route();
  if (drawerOpen && view === 'board' && id) { const main = $('#main'); main.innerHTML = renderBoard(); main.querySelectorAll('.view, .card').forEach(el => el.style.animation = 'none'); renderChrome(); }
  else render();
}

// ——— events ———
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-issue],[data-act],[data-stage],[data-watch],[data-receipt]'); if (!t) return;
  if (t.dataset.issue) location.hash = `#/board/${encodeURIComponent(t.dataset.issue)}`;
  else if (t.dataset.stage) setStage(t.dataset.stage, t);
  else if (t.dataset.act === 'close') location.hash = '#/board';
  else if (t.dataset.act === 'reload') { store.error = null; render(); refresh(); }
  else if (t.dataset.act === 'reread') { store.issueError = null; store.issue = null; renderDrawer(); loadIssue(route().id); }
  else if (t.dataset.act === 'simulate') { t.setAttribute('aria-busy', 'true'); try { const r = await api('/api/demo/activity', {}); toast(`New comment observed on #${r.number}`); } catch (err) { toast(err.message, 'err'); } refresh(); }
  else if (t.dataset.watch) { t.setAttribute('aria-busy', 'true'); try { await api('/api/watch', { action: t.dataset.watch });
      toast({ stop: 'Watcher paused — cursors preserved', start: 'Watcher started', retryNotice: 'Notice resent' }[t.dataset.watch]); } catch (err) { toast(err.message, 'err'); } refresh(); }
  else if (t.dataset.receipt) { t.setAttribute('aria-busy', 'true'); try { await api(`/api/notices/${encodeURIComponent(t.dataset.receipt)}/receipt`, {}); toast('Receipt recorded'); } catch (err) { toast(err.message, 'err'); } refresh(); }
});
$('#scrim').addEventListener('click', () => { location.hash = '#/board'; });
$('#watch-pill').addEventListener('click', () => { location.hash = '#/notices'; });
document.addEventListener('submit', e => { if (e.target.id === 'composer') { e.preventDefault(); submitComment(); } });
document.addEventListener('keydown', e => {
  if (e.target.id === 'composer-text' && e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submitComment(); return; }
  if (e.key === 'Escape' && !$('#drawer').hidden) { location.hash = '#/board'; return; }
  if (!$('#drawer').hidden && e.key === 'Tab') { // keep focus inside the dialog
    const f = [...$('#drawer').querySelectorAll('button, a[href], textarea')].filter(el => !el.disabled); if (!f.length) return;
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f.at(-1).focus(); }
    else if (!e.shiftKey && document.activeElement === f.at(-1)) { e.preventDefault(); f[0].focus(); }
  }
  if (/INPUT|TEXTAREA/.test(e.target.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
  const go = { 1: '#/board', 2: '#/notices', 3: '#/scope' }[e.key]; if (go) location.hash = go;
});
$('#theme-toggle').addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next; localStorage.setItem('theme', next);
});
window.addEventListener('hashchange', render);

(async function boot() {
  render();
  try { store.meta = await api('/api/meta'); } catch (e) { store.error = e; render(); return; }
  await refresh();
  const every = Math.max(4000, Math.min(store.meta.config.pollIntervalMs, 30000));
  setInterval(() => { if (!document.hidden) refresh(); }, every);
})();

#!/usr/bin/env node
// Coordinator Console — a thin local HTTP layer over the real ProjectController.
//   node console/server.mjs --demo                 in-memory GitHub, safe to explore
//   node console/server.mjs --workspace <dir>      reads <dir>/.pi/github-project.json, uses `gh`
// Binds to 127.0.0.1 only. The browser acts as the bound Manager session, so it
// is subject to exactly the same revision, viewer and scope checks as Pi tools.
import http from 'node:http';
import { readFile, lstat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { ProjectController } from '../extensions/github-project/controller.mjs';
import { GitHub } from '../extensions/github-project/github.mjs';
import { FileState, newState, validateState } from '../extensions/github-project/state.mjs';
import { clone } from '../extensions/github-project/domain.mjs';
import { DemoGitHub, demoConfig } from './demo.mjs';

const args = process.argv.slice(2);
const flag = name => { const i = args.indexOf(name); return i >= 0 ? (args[i + 1] ?? true) : undefined; };
const demo = args.includes('--demo') || !flag('--workspace');
const port = Number(flag('--port') ?? process.env.PORT ?? 4317);
const root = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(root, 'public');

class MemoryState {
  async load(config) { return this.value ? validateState(this.value, config) : newState(config); }
  async save(state) { this.value = clone(state); }
}

let config, github, store;
if (demo) { config = demoConfig; github = new DemoGitHub(config); store = new MemoryState(); }
else {
  const workspace = path.resolve(flag('--workspace'));
  const file = path.join(workspace, '.pi', 'github-project.json');
  if ((await lstat(file)).isSymbolicLink()) throw new Error('Configuration must not be a symlink');
  config = JSON.parse(await readFile(file, 'utf8')); github = new GitHub(); store = new FileState(workspace);
}

// Host adapter: the console stands in for the Pi Manager session. Notices the
// controller "sends" land in an inbox; the operator confirms receipt explicitly.
const inbox = []; const receipts = new Set(); const reports = [];
const host = {
  sessionId: () => config.mainSessionId, canManage: () => true, isIdle: () => true, hasPendingMessages: () => false,
  hasNotice: id => receipts.has(id),
  send: text => { const id = text.match(/\[pi-github-notice:([^\]]+)\]/)?.[1];
    inbox.unshift({ id, text, sentAt: new Date().toISOString(), received: false }); inbox.splice(50); },
  report: text => { reports.unshift({ text, at: new Date().toISOString() }); reports.splice(20); },
};
const controller = new ProjectController({ config, github, store, host });
const started = controller.start({ selectOwner: true }).catch(e => host.report(`Watcher could not start: ${e.message}`));

const strip = ({ ownCommentIds, observation, ...rest }) => rest;
const watch = () => ({ active: controller.active, enabled: controller.state?.enabled ?? false, paused: controller.state?.paused ?? false,
  pendingChanges: (controller.state?.pending?.changes.length ?? 0) + (controller.state?.delivery?.changes.length ?? 0),
  awaitingReceipt: !!controller.state?.delivery, pollIntervalMs: controller.config.pollIntervalMs,
  mainSessionId: controller.config.mainSessionId, reports });

const routes = [
  ['GET', /^\/api\/meta$/, async () => ({ mode: demo ? 'demo' : 'live', config: controller.config,
    viewer: await github.viewer().catch(() => null) })],
  ['GET', /^\/api\/project$/, async () => { const p = await controller.readProject();
    return { ...p, issues: p.issues.map(strip), watch: watch() }; }],
  ['GET', /^\/api\/issues\/([^/]+)$/, async ([id]) => { const issue = await controller.readIssue(id);
    return { ...strip(issue), ownCommentIds: issue.ownCommentIds }; }],
  ['POST', /^\/api\/issues\/([^/]+)\/comment$/, ([id], b) =>
    controller.comment({ issueId: id, expectedRevision: b.expectedRevision, requestId: b.requestId ?? randomUUID(), body: b.body })],
  ['POST', /^\/api\/issues\/([^/]+)\/status$/, ([id], b) =>
    controller.status({ issueId: id, expectedRevision: b.expectedRevision, expectedStatusId: b.expectedStatusId ?? null, stage: b.stage })],
  ['GET', /^\/api\/watch$/, async () => watch()],
  ['POST', /^\/api\/watch$/, async (_, b) => {
    if (b.action === 'stop') await controller.stop({ explicit: true });
    else if (b.action === 'start') await controller.start({ explicit: true });
    else if (b.action === 'retryNotice') { controller.noticeSent = false; await controller.idle(); }
    else if (b.action !== 'status') throw Object.assign(new Error('Unknown watch action'), { status: 400 });
    return watch(); }],
  ['GET', /^\/api\/notices$/, async () => ({ pending: controller.state?.pending ?? null,
    delivery: controller.state?.delivery ?? null, inbox, watch: watch() })],
  ['POST', /^\/api\/notices\/([^/]+)\/receipt$/, async ([id]) => {
    const entry = inbox.find(n => n.id === id); if (!entry) throw Object.assign(new Error('Unknown notice'), { status: 404 });
    receipts.add(id); entry.received = true; await controller.idle(); return { received: true, watch: watch() }; }],
  ['POST', /^\/api\/demo\/activity$/, async () => {
    if (!demo) throw Object.assign(new Error('Only available in demo mode'), { status: 403 });
    const r = github.simulate(); await controller.serial(() => controller.observe()); return r; }],
];

const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.ttf': 'font/ttf', '.svg': 'image/svg+xml' };
const send = (res, status, body, type = 'application/json; charset=utf-8') => {
  res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' });
  res.end(type.startsWith('application/json') ? JSON.stringify(body) : body);
};

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  try {
    if (url.pathname.startsWith('/api/')) {
      if (req.method === 'POST' && req.headers['content-type'] !== 'application/json')
        return send(res, 415, { error: 'JSON body required' });
      await started;
      for (const [method, pattern, handler] of routes) {
        const m = url.pathname.match(pattern);
        if (m && req.method === method) {
          let body = {};
          if (method === 'POST') { let raw = ''; for await (const chunk of req) raw += chunk; body = raw ? JSON.parse(raw) : {}; }
          return send(res, 200, await handler(m.slice(1).map(decodeURIComponent), body));
        }
      }
      return send(res, 404, { error: 'Not found' });
    }
    const file = path.join(publicDir, path.normalize(url.pathname === '/' ? '/index.html' : url.pathname));
    if (!file.startsWith(publicDir)) return send(res, 403, 'Forbidden', 'text/plain');
    const data = await readFile(file).catch(() => null);
    if (!data) return send(res, 200, await readFile(path.join(publicDir, 'index.html')), types['.html']);
    send(res, 200, data, types[path.extname(file)] ?? 'application/octet-stream');
  } catch (error) {
    const msg = String(error?.message ?? error);
    const status = error.status ?? (/read again|changed|Read current|Conflicting|stale/i.test(msg) ? 409 : /required|Unknown|Invalid|mapping/i.test(msg) ? 400 : 502);
    send(res, status, { error: msg });
  }
}).listen(port, '127.0.0.1', () => console.log(`Coordinator Console (${demo ? 'demo' : 'live'}) → http://127.0.0.1:${port}`));

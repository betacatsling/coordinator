import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { registerGitHubProject } from '../extensions/github-project/pi-host.mjs';
import { GitHub } from '../extensions/github-project/github.mjs';
import { clone, validateConfig } from '../extensions/github-project/domain.mjs';
import { config, connection, item, ManualClock } from './fakes.mjs';

// Two independent Pi API facades model two fixed Manager sessions. This is an
// offline extension test, not proof of Termius, Herdr leases or native workers.
const Type = {Object:properties=>({type:'object', properties}), String:()=>({type:'string'}),
  Null:()=>({type:'null'}), Literal:value=>({const:value}), Union:anyOf=>({anyOf}), Optional:value=>value};
const managerTools = ['staff_delegate', 'staff_resume', 'staff_message', 'staff_list'];
const noticeId = text => text.match(/\[pi-github-notice:([^\]]+)\]/)[1];
const tick = () => new Promise(resolve => setImmediate(resolve));

class PiBridge {
  constructor({flag, branch}) {
    this.flag=flag; this.branch=clone(branch); this.active=[...managerTools];
    this.handlers=new Map(); this.tools=new Map(); this.sent=[]; this.reports=[];
  }
  registerFlag=()=>{};
  getFlag=()=>this.flag;
  getActiveTools=()=>this.active;
  registerTool=tool=>this.tools.set(tool.name, tool);
  on=(name, handler)=>this.handlers.set(name, [...(this.handlers.get(name) ?? []), handler]);
  sendUserMessage=(text, options)=>this.sent.push({text, options});
  async emit(name, ctx, event={}) {
    for (const handler of this.handlers.get(name) ?? []) await handler(event, ctx);
  }
  receive(text=this.sent.at(-1)?.text) {
    assert.ok(text, 'a notice must exist before its transcript receipt');
    this.branch.push({type:'message', message:{role:'user', content:[{type:'text', text}]}});
  }
}

function projectConfig(key, sameRepository) {
  return validateConfig({...clone(config), repository:sameRepository ? 'example/shared' : `example/${key}`,
    projectId:`PROJECT_${key}`, mainSessionId:`manager-${key}`,
    statusField:{id:`FIELD_${key}`, name:'Status', options:Object.fromEntries(
      Object.entries(config.statusField.options).map(([stage, option]) =>
        [stage, {...option, id:`${key}_${option.id}`}]))}});
}

// One shared fake GraphQL service is deliberately used by BOTH real GitHub
// adapters. Crossed IDs, repositories, cursors or mutations fail assertions.
class GraphQLFixture {
  constructor(configs) {
    this.configs=configs; this.calls=[]; this.writes=[]; this.boards=new Map(); this.comments=0;
    for (const [index, cfg] of configs.entries()) {
      const cards=[1, 2].map(number => {
        const actualNumber=cfg.repository === 'example/shared' ? index * 100 + number : number;
        const card=item(`${cfg.projectId}_ISSUE_${number}`, actualNumber, cfg.repository);
        card.fieldValues=connection([{field:{id:cfg.statusField.id}, optionId:cfg.statusField.options.ready.id}]);
        card.content.body=`Private task body for ${cfg.projectId}`;
        card.content.comments=connection([1, 2].map(n => ({id:`${card.content.id}_C${n}`,
          body:`${cfg.projectId} comment ${n}`, author:{login:'owner'}})));
        return card;
      });
      this.boards.set(cfg.projectId, {id:cfg.projectId, title:cfg.projectId,
        url:`https://github.com/orgs/example/projects/${index+1}`,
        fields:connection([{id:cfg.statusField.id, name:'Status', options:Object.values(cfg.statusField.options)}]),
        items:connection(cards)});
    }
  }
  board(cfg) {return this.boards.get(cfg.projectId);}
  card(cfg, index=0) {return this.board(cfg).items.nodes[index];}
  append(cfg, body) {
    this.card(cfg).content.comments.nodes.push({id:`EXTERNAL_${++this.comments}`, body, author:{login:'owner'}});
  }
  query = async (query, variables, signal) => {
    this.calls.push({query, variables:clone(variables)});
    await tick(); signal?.throwIfAborted(); // Allow both sessions' requests to interleave.
    if (query.includes('items(first:100')) {
      const board=clone(this.boards.get(variables.id)); assert.ok(board, 'unknown Project ID');
      const expected=`${board.id}_ITEM_PAGE_2`;
      assert.ok(variables.cursor === null || variables.cursor === expected, 'crossed Project cursor');
      // Foreign cards expose only membership metadata, never their body/comments.
      const other=this.configs.find(cfg => cfg.projectId !== board.id);
      board.items.nodes=variables.cursor ? [board.items.nodes[1]] :
        [board.items.nodes[0], ...(other.repository !== this.configs.find(c=>c.projectId===board.id).repository ? [clone(this.card(other))] : [])];
      for (const card of board.items.nodes) {
        const {__typename, id, number, repository}=card.content;
        card.content={__typename, id, number, repository};
      }
      board.items.pageInfo={hasNextPage:!variables.cursor, endCursor:expected};
      return {node:board};
    }
    if (query.includes('repository(owner:$owner,name:$name)')) {
      const repository=`${variables.owner}/${variables.name}`;
      const card=[...this.boards.values()].flatMap(board=>board.items.nodes).find(card =>
        card.content.repository.nameWithOwner === repository && card.content.number === variables.number);
      assert.ok(card, 'unknown fixed repository Issue endpoint');
      const issue=clone(card.content); const expected=`${issue.id}_COMMENT_PAGE_2`;
      assert.ok(variables.cursor === undefined || variables.cursor === expected, 'crossed Issue comment cursor');
      issue.comments.nodes=variables.cursor ? issue.comments.nodes.slice(1) : issue.comments.nodes.slice(0, 1);
      issue.comments.pageInfo={hasNextPage:!variables.cursor, endCursor:expected};
      return {repository:{issue}};
    }
    if (query.includes('viewer')) return {viewer:{login:'owner'}};
    if (query.includes('addComment')) {
      const card=[...this.boards.values()].flatMap(board=>board.items.nodes).find(card=>card.content.id===variables.id);
      assert.ok(card, 'unknown comment target');
      const id=`WRITTEN_${++this.comments}`;
      card.content.comments.nodes.push({id, body:variables.body, author:{login:'owner'}});
      this.writes.push({kind:'comment', ...variables});
      return {addComment:{commentEdge:{node:{id}}}};
    }
    if (query.includes('updateProjectV2ItemFieldValue')) {
      const cfg=this.configs.find(cfg=>cfg.projectId===variables.project);
      assert.ok(cfg, 'unknown status Project'); assert.equal(variables.field, cfg.statusField.id);
      assert.ok(Object.values(cfg.statusField.options).some(option=>option.id===variables.option));
      const card=this.board(cfg).items.nodes.find(card=>card.id===variables.item);
      assert.ok(card, 'status item belongs to the other Project');
      card.fieldValues.nodes[0].optionId=variables.option;
      this.writes.push({kind:'status', ...variables});
      return {updateProjectV2ItemFieldValue:{projectV2Item:{id:card.id}}};
    }
    assert.fail('unexpected GraphQL operation');
  };
}

async function pair(t, {sameRepository=false, flag=true}={}) {
  const root=await mkdtemp(path.join(os.tmpdir(), 'pi-two-projects-'));
  const configs=['alpha', 'beta'].map(key=>projectConfig(key, sameRepository));
  const backend=new GraphQLFixture(configs); const runners=[];
  t.after(async()=>{
    for (const runner of runners) await runner.pi.emit('session_shutdown', runner.ctx);
    await rm(root, {recursive:true, force:true});
  });
  async function launch(index, {id=configs[index].mainSessionId, flag=false, branch=[]}={}) {
    const cfg=configs[index], cwd=path.join(root, `workspace-${index}`);
    await mkdir(path.join(cwd, '.pi'), {recursive:true});
    await writeFile(path.join(cwd, '.pi', 'github-project.json'), JSON.stringify(cfg));
    const pi=new PiBridge({flag, branch}), clock=new ManualClock();
    const ctx={cwd, id, idle:true, pending:false, hasUI:true,
      ui:{setStatus:(_key, text)=>pi.reports.push(text)},
      isIdle(){return this.idle;}, hasPendingMessages(){return this.pending;},
      sessionManager:{getSessionId:()=>ctx.id, getBranch:()=>pi.branch}};
    // Use production FileState, selected by the actual Pi host, with no store override.
    const extension=registerGitHubProject(pi, Type, {github:new GitHub(backend.query), clock});
    const execute=(name, params={})=>pi.tools.get(name).execute('TEST', params, undefined, undefined, ctx);
    const statePath=path.join(cwd, '.pi', 'github-project-state.json');
    const runner={cfg, cwd, pi, clock, ctx, extension, execute, statePath,
      state:async()=>JSON.parse(await readFile(statePath, 'utf8')),
      poll:()=>clock.tick(extension.controller),
      start:()=>pi.emit('session_start', ctx),
      settle:()=>pi.emit('agent_settled', ctx)};
    runners.push(runner); return runner;
  }
  const sessions=await Promise.all([0, 1].map(index=>launch(index, {flag})));
  return {configs, backend, launch, sessions};
}

async function startBoth(sessions) {await Promise.all(sessions.map(session=>session.start()));}
async function acknowledgeBoth(sessions) {
  for (const session of sessions) session.pi.receive();
  await Promise.all(sessions.map(session=>session.settle()));
}
function assertOwnNotices(session, other) {
  for (const {text, options} of session.pi.sent) {
    assert.ok(text.includes(`Scope: ${session.cfg.repository} / ${session.cfg.projectId}.`));
    assert.ok(!text.includes(other.cfg.projectId));
    assert.deepEqual(options, {deliverAs:'followUp', expandPromptTemplates:false});
  }
}

test('two fixed Managers require independent opt-in and only read their own Project/repository', async t=>{
  const {sessions:[a,b], backend}=await pair(t, {flag:false});
  await startBoth([a,b]); assert.equal(backend.calls.length, 0);
  await assert.rejects(a.execute('github_project_watch', {action:'start'}), /default-off/);
  a.pi.flag=true; await a.pi.emit('before_agent_start', a.ctx);
  assert.equal(a.pi.sent.length, 1); assert.equal(b.pi.sent.length, 0);
  assert.equal(b.extension.controller.state.enabled, false);
  await assert.rejects(readFile(b.statePath, 'utf8'), {code:'ENOENT'});
  b.pi.flag=true; await b.pi.emit('before_agent_start', b.ctx);
  for (const [own, other] of [[a,b], [b,a]]) {
    const snapshot=(await own.execute('github_project_read')).details;
    assert.equal(snapshot.id, own.cfg.projectId);
    assert.deepEqual(snapshot.issues.map(issue=>issue.number), [1,2]);
    assert.ok(snapshot.issues.every(issue=>issue.url.includes(`/${own.cfg.repository}/`)));
    assert.deepEqual(Object.keys((await own.state()).observed), snapshot.issues.map(issue=>issue.id));
    assertOwnNotices(own, other); assert.equal(own.clock.jobs.size, 1);
  }
  assert.equal(backend.writes.length, 0);
});

test('simultaneous Project and comment pagination keeps every cursor and repository endpoint separate', async t=>{
  const {sessions:[a,b], backend}=await pair(t);
  await startBoth([a,b]);
  for (const own of [a,b]) {
    assert.deepEqual(backend.calls.filter(call=>call.variables.id===own.cfg.projectId).map(call=>call.variables.cursor),
      [null, `${own.cfg.projectId}_ITEM_PAGE_2`]);
    const [owner,name]=own.cfg.repository.split('/');
    const issueCalls=backend.calls.filter(call=>call.variables.owner===owner && call.variables.name===name);
    assert.deepEqual(issueCalls.map(call=>call.variables), [1,2].flatMap(number=>[
      {owner,name,number}, {owner,name,number,cursor:`${own.cfg.projectId}_ISSUE_${number}_COMMENT_PAGE_2`} ]));
    const issue=(await own.execute('github_project_read', {issueId:backend.card(own.cfg).content.id})).details;
    assert.equal(issue.comments.length, 2);
    assert.ok(issue.comments.every(comment=>comment.body.startsWith(own.cfg.projectId)));
  }
  assert.equal(backend.writes.length, 0);
});

test('busy/pending-input Managers coalesce independently and one session receipt cannot acknowledge the other', async t=>{
  const {sessions:[a,b], backend}=await pair(t);
  a.ctx.idle=false; b.ctx.pending=true;
  await startBoth([a,b]);
  backend.append(a.cfg, 'alpha update'); backend.append(b.cfg, 'beta update');
  for (let repeat=0; repeat<2; repeat++) await Promise.all([a.poll(), b.poll()]);
  assert.equal(a.pi.sent.length+b.pi.sent.length, 0);
  const pendingA=(await a.state()).pending, pendingB=(await b.state()).pending;
  assert.notEqual(pendingA.id, pendingB.id);
  assert.ok(pendingA.changes.every(change=>change.issueId.startsWith(a.cfg.projectId)));
  assert.ok(pendingB.changes.every(change=>change.issueId.startsWith(b.cfg.projectId)));
  a.ctx.idle=true; await a.settle(); assert.equal(a.pi.sent.length, 1); assert.equal(b.pi.sent.length, 0);
  b.pi.receive(a.pi.sent[0].text); b.ctx.pending=false; await b.settle();
  assert.equal(b.pi.sent.length, 1); assert.equal((await b.state()).delivery.id, pendingB.id);
  await b.settle(); assert.equal((await b.state()).delivery.id, pendingB.id);
  a.pi.receive(); await a.settle(); assert.equal((await a.state()).delivery, null);
  assert.equal((await b.state()).delivery.id, pendingB.id);
  b.pi.receive(); await b.settle(); assert.equal((await b.state()).delivery, null);
  assertOwnNotices(a,b); assertOwnNotices(b,a);
});

test('file-backed restart recovers each in-flight and pending batch without cross-delivery', async t=>{
  const {sessions:[a,b], backend, launch}=await pair(t);
  await startBoth([a,b]);
  const firstA=(await a.state()).delivery.id, firstB=(await b.state()).delivery.id;
  backend.append(a.cfg, 'alpha second batch'); backend.append(b.cfg, 'beta second batch');
  await Promise.all([a.poll(), b.poll()]);
  const pendingA=(await a.state()).pending.id, pendingB=(await b.state()).pending.id;
  // Alpha crashes before transcript append; beta persists its receipt but crashes
  // before the extension sees it. Fresh bridge/controller/store instances follow.
  b.pi.receive();
  await Promise.all([a.pi.emit('session_shutdown',a.ctx), b.pi.emit('session_shutdown',b.ctx)]);
  const resumedA=await launch(0), resumedB=await launch(1, {branch:b.pi.branch});
  await startBoth([resumedA,resumedB]);
  assert.equal(noticeId(resumedA.pi.sent[0].text), firstA);
  assert.equal((await resumedA.state()).pending.id, pendingA);
  assert.equal(noticeId(resumedB.pi.sent[0].text), pendingB);
  assert.notEqual(noticeId(resumedB.pi.sent[0].text), firstB);
  assertOwnNotices(resumedA,resumedB); assertOwnNotices(resumedB,resumedA);
  resumedA.pi.receive(); await resumedA.settle();
  assert.equal(noticeId(resumedA.pi.sent[1].text), pendingA);
  await acknowledgeBoth([resumedA,resumedB]);
  assert.equal((await resumedA.state()).pending, null); assert.equal((await resumedB.state()).pending, null);
  await Promise.all([resumedA.pi.emit('session_shutdown',resumedA.ctx), resumedB.pi.emit('session_shutdown',resumedB.ctx)]);
  const finalA=await launch(0, {branch:resumedA.pi.branch}), finalB=await launch(1, {branch:resumedB.pi.branch});
  await startBoth([finalA,finalB]);
  assert.equal(finalA.pi.sent.length+finalB.pi.sent.length, 0, 'persisted receipts suppress unchanged replay');
  backend.append(b.cfg, 'beta only after restart'); await Promise.all([finalA.poll(), finalB.poll()]);
  assert.equal(finalA.pi.sent.length, 0); assert.equal(finalB.pi.sent.length, 1);
  assertOwnNotices(finalB,finalA);
});

test('foreign repository Issue reads and mutations are rejected before any remote write', async t=>{
  const {sessions:[a,b], backend}=await pair(t); await startBoth([a,b]);
  for (const [own, other] of [[a,b],[b,a]]) {
    const ownId=backend.card(own.cfg).content.id, foreignId=backend.card(other.cfg).content.id;
    const local=(await own.execute('github_project_read', {issueId:ownId})).details;
    const foreign=(await other.execute('github_project_read', {issueId:foreignId})).details;
    await assert.rejects(own.execute('github_project_read', {issueId:foreignId}), /outside configured/);
    await assert.rejects(own.execute('github_issue_comment', {issueId:foreignId, expectedRevision:foreign.revision,
      requestId:'foreign', body:'must not write'}), /Read current Issue/);
    await assert.rejects(own.execute('github_project_status', {issueId:foreignId, expectedRevision:foreign.revision,
      expectedStatusId:foreign.statusId, stage:'done'}), /Read current Issue/);
    // A previously read Issue that moves outside the repository cannot use the
    // cached revision to bypass the fresh scope check on either write tool.
    backend.card(own.cfg).content.repository.nameWithOwner='example/foreign';
    for (const [name, params] of [
      ['github_issue_comment', {requestId:'moved', body:'must not write'}],
      ['github_project_status', {expectedStatusId:local.statusId, stage:'done'}],
    ]) await assert.rejects(own.execute(name, {issueId:ownId, expectedRevision:local.revision, ...params}), /outside configured/);
    backend.card(own.cfg).content.repository.nameWithOwner=own.cfg.repository;
  }
  assert.deepEqual(backend.writes, []);
});

test('two Projects in the same repository still reject each other\'s Issue membership', async t=>{
  const {sessions:[a,b], backend}=await pair(t, {sameRepository:true}); await startBoth([a,b]);
  for (const [own, other] of [[a,b],[b,a]]) {
    const foreignId=backend.card(other.cfg).content.id;
    await assert.rejects(own.execute('github_project_read', {issueId:foreignId}), /outside configured/);
    assert.ok(Object.keys((await own.state()).observed).every(id=>id.startsWith(own.cfg.projectId)));
    assertOwnNotices(own,other);
  }
  assert.deepEqual(backend.writes, []);
});

test('parallel authorized fake writes preserve exact Project/item/status IDs and separate retry records', async t=>{
  const {sessions:[a,b], backend}=await pair(t); await startBoth([a,b]); await acknowledgeBoth([a,b]);
  const reads=await Promise.all([a,b].map(own=>own.execute('github_project_read', {issueId:backend.card(own.cfg).content.id})));
  await Promise.all([a,b].map((own,index)=>own.execute('github_issue_comment', {
    issueId:reads[index].details.id, expectedRevision:reads[index].details.revision,
    requestId:'same-request-id', body:`Reviewed ${own.cfg.projectId}`})));
  await Promise.all([a,b].map((own,index)=>own.execute('github_issue_comment', {
    issueId:reads[index].details.id, expectedRevision:reads[index].details.revision,
    requestId:'same-request-id', body:`Reviewed ${own.cfg.projectId}`})));
  await Promise.all([a,b].map((own,index)=>own.execute('github_project_status', {
    issueId:reads[index].details.id, expectedRevision:reads[index].details.revision,
    expectedStatusId:reads[index].details.statusId, stage:'done'})));
  const comments=backend.writes.filter(write=>write.kind==='comment'); assert.equal(comments.length,2);
  assert.notEqual(comments[0].body.match(/<!--[^>]+-->/)[0], comments[1].body.match(/<!--[^>]+-->/)[0]);
  for (const own of [a,b]) {
    const writes=backend.writes.filter(write=>write.kind==='status' && write.project===own.cfg.projectId);
    assert.deepEqual(writes, [{kind:'status', project:own.cfg.projectId, item:backend.card(own.cfg).id,
      field:own.cfg.statusField.id, option:own.cfg.statusField.options.done.id}]);
    assert.equal(Object.keys((await own.state()).ownComments).length, 1);
    assert.ok(!(await readFile(own.statePath,'utf8')).includes('Reviewed'));
  }
  await Promise.all([a.poll(),b.poll()]);
  assert.equal(a.pi.sent.length,1); assert.equal(b.pi.sent.length,1);
});

test('forks and swapped Manager IDs inherit neither ownership nor tools while both owners continue', async t=>{
  const {sessions:[a,b], backend, launch}=await pair(t); await startBoth([a,b]); await acknowledgeBoth([a,b]);
  const records=await Promise.all([a,b].map(own=>readFile(own.statePath,'utf8')));
  const calls=backend.calls.length;
  for (const [index, own, other] of [[0,a,b],[1,b,a]]) {
    for (const id of [`${own.cfg.mainSessionId}-fork`, other.cfg.mainSessionId]) {
      const fork=await launch(index, {id, flag:true, branch:own.pi.branch}); await fork.start();
      await fork.pi.emit('before_agent_start',fork.ctx);
      for (const name of fork.pi.tools.keys()) await assert.rejects(fork.execute(name), /bind the Manager/);
      assert.equal(fork.pi.sent.length,0); assert.equal(fork.clock.jobs.size,0);
    }
  }
  assert.equal(backend.calls.length,calls);
  assert.deepEqual(await Promise.all([a,b].map(own=>readFile(own.statePath,'utf8'))),records);
  backend.append(a.cfg,'owner alpha continues'); backend.append(b.cfg,'owner beta continues');
  await Promise.all([a.poll(),b.poll()]); assert.equal(a.pi.sent.length,2); assert.equal(b.pi.sent.length,2);
  assertOwnNotices(a,b); assertOwnNotices(b,a);
});

test('wrong persisted Project state fails closed without overwriting either workspace', async t=>{
  const {sessions:[a,b], backend, launch}=await pair(t); await startBoth([a,b]);
  await Promise.all([a.pi.emit('session_shutdown',a.ctx),b.pi.emit('session_shutdown',b.ctx)]);
  const alpha=await readFile(a.statePath,'utf8'), beta=await readFile(b.statePath,'utf8');
  await writeFile(b.statePath,alpha); const calls=backend.calls.length;
  const resumed=await launch(1); await resumed.start();
  await assert.rejects(resumed.execute('github_project_read'), /scope\/schema/);
  assert.equal(backend.calls.length,calls); assert.equal(resumed.pi.sent.length,0); assert.equal(resumed.clock.jobs.size,0);
  assert.equal(await readFile(a.statePath,'utf8'),alpha); assert.equal(await readFile(b.statePath,'utf8'),alpha);
  await writeFile(b.statePath,beta); // Restore the test fixture; no automatic state rebinding.
});

test('pausing or losing Manager capability in one session does not stop the other Project', async t=>{
  const {sessions:[a,b],backend}=await pair(t); await startBoth([a,b]); await acknowledgeBoth([a,b]);
  await a.execute('github_project_watch',{action:'stop'});
  backend.append(a.cfg,'alpha paused update'); backend.append(b.cfg,'beta active update');
  await Promise.all([a.poll(),b.poll()]); assert.equal(a.pi.sent.length,1); assert.equal(b.pi.sent.length,2);
  assert.equal(a.clock.jobs.size,0); assert.equal(b.clock.jobs.size,1);
  await a.execute('github_project_watch',{action:'start'}); assert.equal(a.pi.sent.length,2);
  a.pi.active=['agent_delegate']; await a.pi.emit('tool_result',a.ctx);
  await assert.rejects(a.execute('github_project_read'),/Manager tools/);
  assert.equal(a.clock.jobs.size,0); assert.equal(b.clock.jobs.size,1);
  b.pi.receive(); await b.settle(); backend.append(b.cfg,'beta keeps going'); await b.poll();
  assert.equal(b.pi.sent.length,3); assertOwnNotices(b,a);
});

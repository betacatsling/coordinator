import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,mkdir,writeFile,rm } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { registerGitHubProject } from '../extensions/github-project/pi-host.mjs';
import { MemoryState } from '../extensions/github-project/state.mjs';
import { config,FakeGitHub,ManualClock,deferred,project } from './fakes.mjs';

const Type={Object:properties=>({type:'object',properties}),String:()=>({type:'string'}),Boolean:()=>({type:'boolean'}),
  Null:()=>({type:'null'}),Literal:constValue=>({const:constValue}),Union:anyOf=>({anyOf}),Optional:value=>value};
class FakePi {
  constructor(){this.handlers=new Map();this.tools=new Map();this.flag=false;this.sent=[];this.branch=[];
    this.active=['staff_delegate','staff_resume','staff_message','staff_list'];this.hooks=0;this.charters=0;}
  registerFlag=(name,options)=>{assert.equal(name,'github-project-manager');assert.equal(options.default,false);};
  getFlag=()=>this.flag;
  getActiveTools=()=>this.active;
  registerTool=tool=>this.tools.set(tool.name,tool);
  on=(name,handler)=>{const entries=this.handlers.get(name)??[];entries.push(handler);this.handlers.set(name,entries);};
  async emit(name,ctx,event={}){for(const handler of this.handlers.get(name)??[])await handler(event,ctx);}
  sendUserMessage=(text,options)=>{this.sent.push({text,options});};
  receive(){for(const {text} of this.sent)if(!this.branch.some(e=>e.message.content[0].text===text))
    this.branch.push({type:'message',message:{role:'user',content:[{type:'text',text}]}});}
}
async function setup(t,{id=config.mainSessionId,flag=true,manager=true}={}){
  const cwd=await mkdtemp(path.join(os.tmpdir(),'pi-github-test-'));t.after(()=>rm(cwd,{recursive:true,force:true}));
  await mkdir(path.join(cwd,'.pi'));await writeFile(path.join(cwd,'.pi','github-project.json'),JSON.stringify(config));
  const pi=new FakePi();pi.flag=flag;if(!manager)pi.active=['agent_delegate'];
  const github=new FakeGitHub(),store=new MemoryState(),clock=new ManualClock();
  const ctx={cwd,id,idle:true,pending:false,hasUI:true,ui:{setStatus:()=>{}},isIdle(){return this.idle;},hasPendingMessages(){return this.pending;},
    sessionManager:{getSessionId:()=>ctx.id,getBranch:()=>pi.branch}};
  const extension=registerGitHubProject(pi,Type,{github,store,clock});
  t.after(async()=>{await pi.emit('session_shutdown',ctx);});
  const execute=(name,params={})=>pi.tools.get(name).execute('CALL',params,undefined,undefined,ctx);
  return {cwd,pi,github,store,clock,ctx,extension,execute};
}
test('factory registers only tools/handlers; no resources or GitHub read before session_start',async t=>{
  const f=await setup(t);assert.equal(f.github.fetches,0);assert.equal(f.clock.jobs.size,0);
  assert.deepEqual([...f.pi.tools.keys()],['github_project_read','github_issue_read','github_issue_comment','github_project_status','github_project_watch']);
  await f.pi.emit('session_start',f.ctx,{reason:'startup'});assert.equal(f.github.fetches,1);assert.equal(f.pi.sent.length,1);
  f.pi.receive();await f.pi.emit('agent_settled',f.ctx);assert.equal(f.store.value.delivery,null);
});
test('default-off startup cannot be activated by a tool without initial CLI selection',async t=>{
  const f=await setup(t,{flag:false});await f.pi.emit('session_start',f.ctx);assert.equal(f.github.fetches,0);
  await assert.rejects(f.execute('github_project_watch',{action:'start'}),/default-off/);
});
test('global extension in Lead/Agent never polls or writes, even with inherited flag',async t=>{
  for(const options of [{id:'lead',flag:true},{id:'agent',flag:true},{manager:false,flag:true}]){
    const f=await setup(t,options);await f.pi.emit('session_start',f.ctx);await f.pi.emit('before_agent_start',f.ctx);
    assert.equal(f.github.fetches,0);assert.equal(f.clock.jobs.size,0);await assert.rejects(f.execute('github_project_read'));
  }
});
test('owner resume without CLI flag recovers enabled record; new/fork stays inactive',async t=>{
  const f=await setup(t);await f.pi.emit('session_start',f.ctx);f.pi.receive();await f.pi.emit('agent_settled',f.ctx);
  await f.pi.emit('session_shutdown',f.ctx);f.pi.flag=false;
  await f.pi.emit('session_start',f.ctx,{reason:'resume'});assert.equal(f.github.fetches,2);assert.equal(f.pi.sent.length,1);
  f.ctx.id='forked';await f.pi.emit('session_start',f.ctx,{reason:'fork'});assert.equal(f.github.fetches,2);assert.equal(f.clock.jobs.size,0);
  f.ctx.id='new';await f.pi.emit('session_start',f.ctx,{reason:'new'});assert.equal(f.github.fetches,2);
});
test('reload stops prior generation; stale delayed responses cannot notify new runtime',async t=>{
  const f=await setup(t);await f.pi.emit('session_start',f.ctx);f.pi.receive();await f.pi.emit('agent_settled',f.ctx);
  const old=f.extension.controller;const waiting=deferred();const original=f.github.fetchProject.bind(f.github);
  let delayed=true;f.github.fetchProject=async()=>{if(delayed){delayed=false;return waiting.promise;}return original();};
  const poll=old.serial(()=>old.observe(old.abort.signal));await new Promise(r=>setImmediate(r));
  const reload=f.pi.emit('session_start',f.ctx,{reason:'reload'});waiting.resolve(project());
  await assert.rejects(poll,/bound|lifecycle/);await reload;
  assert.notEqual(f.extension.controller,old);assert.equal(f.clock.jobs.size,1);assert.equal(f.pi.sent.length,1);
});
test('shutdown during initial fetch aborts and is idempotent without a wake',async t=>{
  const f=await setup(t);const waiting=deferred();f.github.fetchProject=async()=>waiting.promise;
  const startup=f.pi.emit('session_start',f.ctx);await new Promise(r=>setImmediate(r));
  // Wait until the test request has actually entered the controller.
  for(let n=0;n<20 && !f.extension.controller?.active;n++)await new Promise(r=>setImmediate(r));
  const shutdown=f.pi.emit('session_shutdown',f.ctx);waiting.resolve(project());await startup;await shutdown;
  assert.equal(f.pi.sent.length,0);assert.equal(f.clock.jobs.size,0);await f.pi.emit('session_shutdown',f.ctx);
});
test('notification uses public user path and remains queued until persisted user transcript receipt',async t=>{
  const f=await setup(t);await f.pi.emit('session_start',f.ctx);
  assert.deepEqual(f.pi.sent[0].options,{deliverAs:'followUp',expandPromptTemplates:false});assert.ok(f.store.value.delivery);
  // Simulate public Pi user-message preflight then persisted message append.
  f.pi.on('before_agent_start',()=>{f.pi.charters++;});
  await f.pi.emit('before_agent_start',f.ctx);assert.equal(f.pi.charters,1);
  await f.pi.emit('agent_end',f.ctx);assert.ok(f.store.value.delivery,'an event alone is not durable receipt');
  f.pi.receive();await f.pi.emit('agent_settled',f.ctx);assert.equal(f.store.value.delivery,null);
});
test('agent_settled drains existing batch without polling GitHub; stop persists pause',async t=>{
  const f=await setup(t);f.ctx.idle=false;await f.pi.emit('session_start',f.ctx);assert.equal(f.pi.sent.length,0);
  f.ctx.idle=true;await f.pi.emit('agent_settled',f.ctx);assert.equal(f.pi.sent.length,1);assert.equal(f.github.fetches,1);
  const result=await f.execute('github_project_watch',{action:'stop'});assert.equal(result.details.paused,true);assert.equal(f.clock.jobs.size,0);
  await f.pi.emit('session_start',f.ctx,{reason:'reload'});assert.equal(f.github.fetches,1);
});
test('Manager capability loss stops timer; tools cannot bypass lost role',async t=>{
  const f=await setup(t);await f.pi.emit('session_start',f.ctx);f.pi.active=['agent_delegate'];
  await f.pi.emit('tool_result',f.ctx);assert.equal(f.clock.jobs.size,0);await assert.rejects(f.execute('github_issue_read',{issueId:'I1'}),/Manager tools/);
});
test('configuration edits require explicit reload reconciliation and cannot broaden active scope',async t=>{
  const f=await setup(t);await f.pi.emit('session_start',f.ctx);
  await writeFile(path.join(f.cwd,'.pi','github-project.json'),JSON.stringify({...config,repository:'other/repo'}));
  await assert.rejects(f.execute('github_project_read'),/Configuration changed/);assert.equal(f.clock.jobs.size,0);
  await f.pi.emit('session_start',f.ctx,{reason:'reload'});assert.equal(f.github.fetches,1);assert.equal(f.pi.sent.length,1);
});

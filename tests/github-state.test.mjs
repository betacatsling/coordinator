import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,mkdir,readFile,writeFile,stat,symlink,rm,readdir } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { GitHub } from '../extensions/github-project/github.mjs';
import { FileState,newState,validateState } from '../extensions/github-project/state.mjs';
import { validateConfig,normalizeProject,digest } from '../extensions/github-project/domain.mjs';
import { config,project,item,connection } from './fakes.mjs';

test('Project item and Issue comment pagination fetches all pages before normalization',async()=>{
  const calls=[];
  const github=new GitHub(async(query,variables)=>{
    calls.push(variables);
    if(query.includes('items(first:100')){
      const p=project(variables.cursor ? [item('I2',2)] : [item()]);
      if(!variables.cursor)p.items.pageInfo={hasNextPage:true,endCursor:'ITEM_CURSOR'};
      return {node:p};
    }
    const issue=item(variables.number===1?'I1':'I2',variables.number).content;
    if(query.includes('after:$cursor'))issue.comments=connection([{id:'SECOND',body:'later page',author:{login:'outsider'}}]);
    else if(variables.number===1)issue.comments.pageInfo={hasNextPage:true,endCursor:'COMMENT_CURSOR'};
    return {repository:{issue}};
  });
  const snapshot=normalizeProject(await github.fetchProject(config),validateConfig(config));
  assert.equal(snapshot.issues.length,2);assert.equal(snapshot.issues[0].comments[0].body,'later page');
  assert.deepEqual(calls,[{id:config.projectId,cursor:null},{id:config.projectId,cursor:'ITEM_CURSOR'},
    {owner:'example',name:'repo',number:1},{owner:'example',name:'repo',number:1,cursor:'COMMENT_CURSOR'},
    {owner:'example',name:'repo',number:2}]);
});
test('pagination with missing/repeated cursors fails instead of looping',async()=>{
  for(const cursor of [null,'same']) {
    const github=new GitHub(async()=>{const p=project();p.items.pageInfo={hasNextPage:true,endCursor:cursor};return {node:p};});
    await assert.rejects(github.fetchProject(config),/pagination/);
  }
});
test('foreign repo bodies/comments are never requested; draft Issue cards ignored',async()=>{
  const calls=[];const foreign=item('F',3,'foreign/repo');
  const github=new GitHub(async(query,variables)=>{
    calls.push({query,variables});
    if(query.includes('items(first:100')) {
      assert.ok(!query.includes('body'));assert.ok(!query.includes('comments'));assert.ok(!query.includes('author'));
      return {node:project([item(),foreign,{id:'D',content:{__typename:'DraftIssue'}}])};
    }
    assert.deepEqual(variables,{owner:'example',name:'repo',number:1});return {repository:{issue:item().content}};
  });
  const result=normalizeProject(await github.fetchProject(config),validateConfig(config));assert.equal(calls.length,2);assert.equal(result.issues.length,1);
});
test('membership/read identity drift fails closed at fixed repository endpoint',async()=>{
  const calls=[];const github=new GitHub(async(query,variables)=>{
    calls.push(variables);return query.includes('items(first:100') ? {node:project()} : {repository:{issue:item('OTHER',1).content}};
  });
  await assert.rejects(github.fetchProject(config),/identity\/repository changed/);
  assert.deepEqual(calls[1],{owner:'example',name:'repo',number:1});
});
test('comment page identity drift fails closed without reading an arbitrary node',async()=>{
  const github=new GitHub(async(query)=>{
    if(query.includes('items(first:100'))return {node:project()};
    const issue=item(query.includes('after:$cursor')?'OTHER':'I1').content;
    if(!query.includes('after:$cursor'))issue.comments.pageInfo={hasNextPage:true,endCursor:'CURSOR'};
    assert.ok(query.includes('repository(owner:$owner,name:$name)'));
    return {repository:{issue}};
  });
  await assert.rejects(github.fetchProject(config),/identity\/repository changed/);
});
test('GitHub mutations use exact configured node IDs and check returned write confirmation',async()=>{
  const calls=[];const github=new GitHub(async(query,variables)=>{calls.push({query,variables});
    if(query.includes('addComment'))return {addComment:{commentEdge:{node:{id:'C_OK'}}}};
    return {updateProjectV2ItemFieldValue:{projectV2Item:{id:'ITEM_I1'}}};});
  assert.equal(await github.addComment('I1','result'),'C_OK');await github.setStatus(config,{itemId:'ITEM_I1'},'done');
  assert.deepEqual(calls[1].variables,{project:config.projectId,item:'ITEM_I1',field:'FIELD',option:'done'});
  assert.ok(calls[0].query.includes('$body:String!'));
  const rejected=new GitHub(async()=>({}));await assert.rejects(rejected.addComment('I1','body'),/not confirmed/);
  await assert.rejects(rejected.setStatus(config,{itemId:'I'},'done'),/not confirmed/);
});
test('configuration rejects credentials, extra scopes, unmapped stages and invalid repository',()=>{
  for(const candidate of [{...config,token:'SECRET'},{...config,projects:['other']},{...config,repository:'invalid'},
    {...config,statusField:{...config.statusField,options:{...config.statusField.options,unknown:{id:'x',name:'X'}}}}])
    assert.throws(()=>validateConfig(candidate));
});
test('file state round trips atomically, private permissions, no Issue text stored',async t=>{
  const cwd=await mkdtemp(path.join(os.tmpdir(),'pi-state-test-'));t.after(()=>rm(cwd,{recursive:true,force:true}));
  const store=new FileState(cwd);const cfg=validateConfig(config);const state=await store.load(cfg);
  state.enabled=true;state.observed={I1:{hash:'hash',number:1}};await store.save(state);
  assert.deepEqual(await new FileState(cwd).load(cfg),state);assert.equal((await stat(store.file)).mode&0o777,0o600);
  assert.equal((await readdir(path.join(cwd,'.pi'))).filter(f=>f.endsWith('.tmp')).length,0);
  const raw=await readFile(store.file,'utf8');assert.ok(!raw.includes('Do approved work'));
});
test('corrupt state and scope mismatch fail closed without replacing existing record',async t=>{
  const cwd=await mkdtemp(path.join(os.tmpdir(),'pi-state-test-'));t.after(()=>rm(cwd,{recursive:true,force:true}));
  const store=new FileState(cwd);await store.load(validateConfig(config));await writeFile(store.file,'{bad');
  await assert.rejects(store.load(validateConfig(config)));assert.equal(await readFile(store.file,'utf8'),'{bad');
  await store.save(newState(validateConfig(config)));await assert.rejects(store.load(validateConfig({...config,mainSessionId:'other'})),/scope\/schema/);
});
test('symlinked state folder/file cannot redirect writes out of workspace',async t=>{
  const cwd=await mkdtemp(path.join(os.tmpdir(),'pi-state-test-'));const outside=await mkdtemp(path.join(os.tmpdir(),'pi-state-outside-'));
  t.after(()=>Promise.all([rm(cwd,{recursive:true,force:true}),rm(outside,{recursive:true,force:true})]));
  await symlink(outside,path.join(cwd,'.pi'));const store=new FileState(cwd);
  await assert.rejects(store.load(validateConfig(config)),/real workspace/);
  await rm(path.join(cwd,'.pi'));await mkdir(path.join(cwd,'.pi'));await writeFile(path.join(outside,'untouched'),'sentinel');
  await symlink(path.join(outside,'untouched'),store.file);await assert.rejects(store.load(validateConfig(config)),/symlink/);
  assert.equal(await readFile(path.join(outside,'untouched'),'utf8'),'sentinel');
});


test('state binding ignores polling cadence and semantic configuration ordering',()=>{
  const cfg=validateConfig({...config,authorizedUsers:['owner','reviewer']});
  const state=newState(cfg);state.enabled=true;state.pending={id:'NOTICE',changes:[{issueId:'I1',number:1,kind:'changed'}]};
  const reordered=validateConfig({...cfg,pollIntervalMs:60000,authorizedUsers:['reviewer','owner','owner'],
    statusField:{options:Object.fromEntries(Object.entries(cfg.statusField.options).reverse().map(([stage,option])=>
      [stage,{name:option.name,id:option.id}])),name:cfg.statusField.name,id:cfg.statusField.id}});
  assert.deepEqual(validateState(state,reordered),state);
  assert.ok(!Object.hasOwn(state,'owner'),'ownership is part of the one scope fingerprint');
});
test('state binding still rejects every owner, authorization and status mapping change',()=>{
  const cfg=validateConfig(config);const state=newState(cfg);
  const changed=[{repository:'another/repo'},{projectId:'PVT_other'},{mainSessionId:'other-manager'},
    {authorizedUsers:['owner','another-author']},{statusField:{...cfg.statusField,id:'OTHER_FIELD'}},
    {statusField:{...cfg.statusField,name:'Renamed status'}},
    {statusField:{...cfg.statusField,options:{...cfg.statusField.options,done:{id:'OTHER_DONE',name:'Done'}}}},
    {statusField:{...cfg.statusField,options:{...cfg.statusField.options,done:{id:'done',name:'Finished'}}}}];
  for(const change of changed)assert.throws(()=>validateState(state,validateConfig({...cfg,...change})),/scope\/schema/);
});
test('matching legacy state keeps receipts, pause and cursors while dropping duplicate owner data',()=>{
  const cfg=validateConfig(config);const legacy={...newState(cfg),scope:digest(cfg),
    owner:{projectId:cfg.projectId,repository:cfg.repository,mainSessionId:cfg.mainSessionId},enabled:true,paused:true,
    observed:{I1:{hash:'unchanged',number:1,statusId:'ready'}},
    pending:{id:'NEXT',changes:[{issueId:'I2',number:2,kind:'added'}]},
    delivery:{id:'SENT',changes:[{issueId:'I1',number:1,kind:'changed'}]},ownComments:{C1:{hash:'comment',author:'owner'}}};
  const before=structuredClone(legacy);const current=validateState(legacy,cfg);
  assert.deepEqual(legacy,before,'loading must not mutate the input record');
  const {owner,scope,...preserved}=legacy;
  assert.deepEqual(current,{...preserved,scope:newState(cfg).scope});
  assert.deepEqual(validateState(current,validateConfig({...cfg,pollIntervalMs:5000})),current);
});
test('legacy state cannot bypass authorization or timing uncertainty with a matching owner tuple',()=>{
  const cfg=validateConfig(config);const legacy={...newState(cfg),scope:digest(cfg),
    owner:{projectId:cfg.projectId,repository:cfg.repository,mainSessionId:cfg.mainSessionId}};
  // The old hash includes its interval but did not store that interval separately.
  for(const change of [{pollIntervalMs:5000},{authorizedUsers:['owner','another-author']}])
    assert.throws(()=>validateState(legacy,validateConfig({...cfg,...change})),/scope\/schema/);
});

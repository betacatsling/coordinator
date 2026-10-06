import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture,start,settle,observe,FakeHost,item} from './fakes.mjs';

const card=f=>f.github.value.items.nodes[0];
async function remove(f) {
  const removed=card(f);f.github.value.items.nodes=[];await observe(f);return removed;
}
async function rejoin(f,removed) {
  const returned=structuredClone(removed);
  // GitHub creates a new Project item when the same Issue joins again.
  returned.id=`${removed.id}_REJOINED`;
  f.github.value.items.nodes=[returned];await observe(f);return returned;
}
async function busyRoundTrip() {
  const f=fixture();await start(f);await settle(f);f.host.idle=false;
  await rejoin(f,await remove(f));return f;
}

test('busy remove/rejoin renders the latest in-scope membership instead of a removed Issue header',async()=>{
  const f=await busyRoundTrip();
  const issue=await f.controller.readIssue('I1');assert.equal(issue.itemId,'ITEM_I1_REJOINED');
  assert.equal(f.host.sent.length,1,'busy observations must not publish an intermediate notice');
  f.host.idle=true;await f.controller.idle();const text=f.host.sent[1].text;
  assert.match(text,/Issue #1:/);assert.match(text,/first observed \/ joined board/);
  assert.doesNotMatch(text,/Issue #1: removed\b/,'the latest observed Issue is back in scope');
});

test('coalesced rejoin retains historical departure without claiming the Issue is currently unwritable',async()=>{
  const f=await busyRoundTrip();
  const events=f.store.value.pending.changes[0].events;
  assert.ok(events.some(e=>e.kind==='removed from scope'),'retain the observed departure');
  assert.ok(events.some(e=>e.kind==='first observed / joined board'),'retain the observed rejoin');
  f.host.idle=true;await f.controller.idle();const text=f.host.sent[1].text;
  assert.match(text,/removed from scope/);assert.match(text,/first observed \/ joined board/);
  // A fresh, authorized fake write demonstrates that present-tense absence is false.
  const issue=await f.controller.readIssue('I1');
  await f.controller.status({issueId:issue.id,expectedRevision:issue.revision,
    expectedStatusId:issue.statusId,stage:'inProgress'});
  assert.equal(f.github.writes.length,1);assert.equal(f.github.writes[0].itemId,'ITEM_I1_REJOINED');
  assert.doesNotMatch(text,/This Issue is no longer in the configured Project\/repository; it cannot be written through this extension\./,
    'a historical departure must not assert the current Issue is out of scope');
});

test('a pending comment followed by departure renders final removed membership and retains the comment',async()=>{
  const f=fixture();await start(f);await settle(f);f.host.idle=false;
  f.github.externalComment('Comment before leaving the board','A','alice');await observe(f);
  await remove(f);await assert.rejects(f.controller.readIssue('I1'),/outside configured repository\/Project scope/);
  f.host.idle=true;await f.controller.idle();const text=f.host.sent[1].text;
  assert.match(text,/Comment before leaving the board/);assert.match(text,/Comment author: @alice/);
  assert.match(text,/removed from scope/);
  assert.match(text,/Issue #1: removed\b/,'the final observed membership must override the earlier changed label');
  assert.doesNotMatch(text,/Issue #1: changed\b/);
});

test('membership round trip preserves distinct pending comments and the latest excerpt for each ID',async()=>{
  const f=fixture();await start(f);await settle(f);f.host.idle=false;
  f.github.externalComment('Before departure','A','alice');await observe(f);
  const removed=await remove(f);
  removed.content.comments.nodes[0].body='Edited while away';
  removed.content.comments.nodes.push({id:'B',body:'Second distinct comment',author:{login:'bob'},
    url:'https://github.com/example/repo/issues/1#issuecomment-2'});
  await rejoin(f,removed);await observe(f);
  const events=f.store.value.pending.changes[0].events;
  assert.deepEqual(events.filter(e=>e.commentId).map(e=>e.commentId).sort(),['A','B']);
  assert.equal(events.find(e=>e.commentId==='A').body,'Edited while away');
  assert.equal(events.find(e=>e.commentId==='B').body,'Second distinct comment');
  assert.ok(events.some(e=>e.kind==='removed from scope'));
  assert.ok(events.some(e=>e.kind==='first observed / joined board'));
  f.host.idle=true;await f.controller.idle();const text=f.host.sent[1].text;
  assert.match(text,/Edited while away/);assert.match(text,/Second distinct comment/);
  assert.match(text,/Comment author: @alice/);assert.match(text,/Comment author: @bob/);
  assert.doesNotMatch(text,/Before departure/);
  assert.equal((text.match(/Comment ID: A\b/g)??[]).length,1);
  assert.equal((text.match(/Comment ID: B\b/g)??[]).length,1);
});

test('rejoin after a removal notice is in flight stays in a separate pending batch until receipt',async()=>{
  const f=fixture();await start(f);await settle(f);
  const removed=await remove(f);const frozen=structuredClone(f.store.value.delivery);
  const firstText=f.host.sent[1].text;assert.match(firstText,/removed from scope/);
  removed.content.comments.nodes.push({id:'B',body:'Only after rejoin',author:{login:'bob'}});
  await rejoin(f,removed);
  assert.deepEqual(f.store.value.delivery,frozen,'new membership must not rewrite an in-flight snapshot');
  assert.notEqual(f.store.value.pending.id,frozen.id);assert.equal(f.host.sent.length,2);
  assert.match(JSON.stringify(f.store.value.pending),/Only after rejoin/);
  assert.doesNotMatch(JSON.stringify(f.store.value.delivery),/Only after rejoin/);
  await settle(f);assert.equal(f.host.sent[1].text,firstText);assert.equal(f.host.sent.length,3);
  const secondText=f.host.sent[2].text;
  assert.match(secondText,/first observed \/ joined board/);assert.match(secondText,/Only after rejoin/);
  assert.doesNotMatch(secondText,/removed from scope/);assert.doesNotMatch(secondText,/Issue #1: removed\b/);
  await settle(f);assert.equal(f.store.value.delivery,null);assert.equal(f.store.value.pending,null);
});

test('restart replays a frozen removal exactly and then independently delivers the newer rejoin',async()=>{
  const f=fixture();await start(f);await settle(f);const removed=await remove(f);
  const firstText=f.host.sent[1].text;const deliveryId=f.store.value.delivery.id;
  removed.content.body='Rejoined task body';await rejoin(f,removed);
  const pendingId=f.store.value.pending.id;await f.controller.stop();
  const retry=fixture({store:f.store,github:f.github,host:new FakeHost()});await retry.controller.start();
  assert.equal(retry.host.sent.length,1);assert.equal(retry.host.sent[0].text,firstText);
  assert.equal(retry.store.value.delivery.id,deliveryId);assert.equal(retry.store.value.pending.id,pendingId);
  await settle(retry);assert.equal(retry.host.sent.length,2);
  assert.equal(retry.store.value.delivery.id,pendingId);
  assert.match(retry.host.sent[1].text,/Rejoined task body/);
  assert.match(retry.host.sent[1].text,/first observed \/ joined board/);
  assert.doesNotMatch(retry.host.sent[1].text,/removed from scope/);
});

test('busy initial reconciliation retains current-task context until a later departure overrides it',async()=>{
  const f=fixture();f.host.idle=false;await start(f);
  f.github.externalComment('During initial reconciliation','A','alice');await observe(f);
  assert.equal(f.store.value.pending.changes[0].kind,'current');
  await remove(f);assert.equal(f.store.value.pending.changes[0].kind,'removed');
  f.host.idle=true;await f.controller.idle();const text=f.host.sent[0].text;
  assert.match(text,/Issue #1: removed\b/);assert.match(text,/current task/);
  assert.match(text,/During initial reconciliation/);assert.match(text,/removed from scope/);
});

test('busy added-task context survives comments but yields to removal and rejoin',async()=>{
  const f=fixture();await start(f);await settle(f);f.host.idle=false;
  f.github.value.items.nodes.unshift(item('I2',2));await observe(f);
  f.github.externalComment('Added task discussion','A','alice');await observe(f);
  assert.equal(f.store.value.pending.changes[0].kind,'added');
  const added=f.github.value.items.nodes.shift();await observe(f);
  assert.equal(f.store.value.pending.changes[0].kind,'removed');
  f.github.value.items.nodes.unshift({...added,id:'ITEM_I2_REJOINED'});await observe(f);
  assert.equal(f.store.value.pending.changes[0].kind,'added');
  f.host.idle=true;await f.controller.idle();const text=f.host.sent[1].text;
  assert.match(text,/Issue #2: added\b/);assert.match(text,/Added task discussion/);
  assert.match(text,/removed from scope/);assert.match(text,/first observed \/ joined board/);
});

test('repeated busy membership round trips always reflect the latest poll and retain event details',async()=>{
  const f=fixture();await start(f);await settle(f);f.host.idle=false;
  for(let i=0;i<3;i++) {
    const removed=await remove(f);assert.equal(f.store.value.pending.changes[0].kind,'removed');
    await rejoin(f,removed);assert.equal(f.store.value.pending.changes[0].kind,'added');
    f.github.externalComment(`Round ${i} discussion`,`ROUND_${i}`,'alice');await observe(f);
    assert.equal(f.store.value.pending.changes[0].kind,'added');
  }
  await remove(f);assert.equal(f.store.value.pending.changes[0].kind,'removed');
  f.host.idle=true;await f.controller.idle();const text=f.host.sent[1].text;
  assert.match(text,/Issue #1: removed\b/);assert.doesNotMatch(text,/Issue #1: added\b/);
  for(let i=0;i<3;i++)assert.match(text,new RegExp(`Round ${i} discussion`));
  assert.match(text,/removed from scope/);assert.match(text,/first observed \/ joined board/);
  assert.doesNotMatch(text,/it cannot be written/);
});

test('restart preserves the coalesced rejoin and its receipt clears the entire pending history',async()=>{
  const f=await busyRoundTrip();const pending=structuredClone(f.store.value.pending);
  await f.controller.stop();
  const retry=fixture({store:f.store,github:f.github,host:new FakeHost()});await retry.controller.start();
  assert.deepEqual(retry.store.value.delivery,pending);
  assert.match(retry.host.sent[0].text,/Issue #1: added\b/);
  assert.match(retry.host.sent[0].text,/removed from scope/);
  assert.match(retry.host.sent[0].text,/first observed \/ joined board/);
  await settle(retry);await observe(retry);assert.equal(retry.host.sent.length,1);
  assert.equal(retry.store.value.pending,null);assert.equal(retry.store.value.delivery,null);
});

test('unchanged restart repairs an older unsent rejoin batch without changing its receipt or history',async()=>{
  const f=await busyRoundTrip();await f.controller.stop();
  const pending=f.store.value.pending,change=pending.changes[0];
  // State written by the earlier controller before a membership fix was loaded.
  change.kind='removed';
  change.events.find(e=>e.kind==='removed from scope').body=
    'This Issue is no longer in the configured Project/repository; it cannot be written through this extension.';
  const history=change.events.map(e=>e.kind),id=pending.id;
  const retry=fixture({store:f.store,github:f.github,host:new FakeHost()});await retry.controller.start();
  assert.equal(retry.store.value.delivery.id,id);
  assert.deepEqual(retry.store.value.delivery.changes[0].events.map(e=>e.kind),history);
  assert.match(retry.host.sent[0].text,/Issue #1: added\b/);
  assert.match(retry.host.sent[0].text,/removed from scope/);
  assert.doesNotMatch(retry.host.sent[0].text,/This Issue is no longer|it cannot be written/);
});

test('unchanged restart repairs an older unsent departure while retaining the pending comment',async()=>{
  const f=fixture();await start(f);await settle(f);f.host.idle=false;
  f.github.externalComment('Preserve before upgrade','A','alice');await observe(f);await remove(f);
  await f.controller.stop();f.store.value.pending.changes[0].kind='changed';
  const id=f.store.value.pending.id;
  const retry=fixture({store:f.store,github:f.github,host:new FakeHost()});await retry.controller.start();
  assert.equal(retry.store.value.delivery.id,id);
  assert.match(retry.host.sent[0].text,/Issue #1: removed\b/);
  assert.match(retry.host.sent[0].text,/Preserve before upgrade/);
  assert.match(retry.host.sent[0].text,/Comment author: @alice/);
});

test('pending normalization never rewrites an older in-flight removal on restart',async()=>{
  const f=fixture();await start(f);await settle(f);const removed=await remove(f);
  await f.controller.stop();const event=f.store.value.delivery.changes[0].events[0];
  const oldBody='This Issue is no longer in the configured Project/repository; it cannot be written through this extension.';
  const oldText=f.host.sent[1].text.replace(event.body,oldBody);event.body=oldBody;
  const frozen=structuredClone(f.store.value.delivery);
  f.github.value.items.nodes=[{...removed,id:'ITEM_I1_REJOINED'}];
  const retry=fixture({store:f.store,github:f.github,host:new FakeHost()});await retry.controller.start();
  assert.deepEqual(retry.store.value.delivery,frozen);assert.equal(retry.host.sent[0].text,oldText);
  assert.equal(retry.store.value.pending.changes[0].kind,'added');
  await settle(retry);assert.match(retry.host.sent[1].text,/Issue #1: added\b/);
  assert.doesNotMatch(retry.host.sent[1].text,/it cannot be written|removed from scope/);
});

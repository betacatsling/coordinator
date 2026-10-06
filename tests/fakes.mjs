import { clone } from '../extensions/github-project/domain.mjs';
import { MemoryState } from '../extensions/github-project/state.mjs';
import { ProjectController } from '../extensions/github-project/controller.mjs';

export const config = {repository:'example/repo', projectId:'PVT_test', mainSessionId:'manager-session', authorizedUsers:['owner'],
  pollIntervalMs:1000, statusField:{id:'FIELD',name:'Status',options:{ready:{id:'ready',name:'Todo'},
    inProgress:{id:'progress',name:'In progress'},inReview:{id:'review',name:'In review'},done:{id:'done',name:'Done'}}}};
export const connection = nodes => ({nodes,pageInfo:{hasNextPage:false}});
export function item(id='I1', number=1, repository=config.repository) {
  return {id:`ITEM_${id}`,fieldValues:connection([{field:{id:'FIELD'},optionId:'ready'}]),content:{__typename:'Issue',id,number,
    title:`Task ${number}`,body:'Do approved work',url:`https://github.com/${repository}/issues/${number}`,state:'OPEN',author:{login:'owner'},
    repository:{nameWithOwner:repository},comments:connection([])}};
}
export function project(items=[item()]) {
  return {id:config.projectId,title:'Tasks',url:'https://github.com/users/example/projects/1',
    fields:connection([{id:'FIELD',name:'Status',options:clone(Object.values(config.statusField.options))}]),items:connection(items)};
}
export class FakeGitHub {
  constructor(value=project()) {this.value=value;this.fetches=0;this.writes=[];this.nextComment=1;}
  async fetchProject() {this.fetches++; return clone(this.value);}
  async viewer() {return 'owner';}
  async addComment(id,body) {
    const commentId=`C${this.nextComment++}`;this.writes.push({operation:'comment',id,body});
    this.value.items.nodes.find(i=>i.content?.id === id).content.comments.nodes.push({id:commentId,body,author:{login:'owner'}});
    return commentId;
  }
  async setStatus(cfg,issue,optionId) {
    this.writes.push({operation:'status',projectId:cfg.projectId,itemId:issue.itemId,optionId});
    this.value.items.nodes.find(i=>i.id === issue.itemId).fieldValues.nodes[0].optionId=optionId;
  }
  externalComment(body='new request', id='EXT', author='owner') {
    this.value.items.nodes[0].content.comments.nodes.push({id,body,author:{login:author}});
  }
}
export class FakeHost {
  constructor() {this.id=config.mainSessionId;this.idle=true;this.manager=true;this.pending=false;this.sent=[];this.receipts=new Set();this.reports=[];}
  sessionId=()=>this.id;
  canManage=()=>this.manager;
  isIdle=()=>this.idle;
  hasPendingMessages=()=>this.pending;
  hasNotice=id=>this.receipts.has(id);
  send=(text,options)=>{this.sent.push({text,options});};
  report=text=>this.reports.push(text);
  acknowledge() {for (const {text} of this.sent) this.receipts.add(text.match(/\[pi-github-notice:([^\]]+)\]/)[1]);}
}
export class ManualClock {
  constructor() {this.jobs=new Map();this.next=1;}
  setTimeout=(fn)=>{const id=this.next++;this.jobs.set(id,fn);return id;};
  clearTimeout=id=>this.jobs.delete(id);
  async tick(controller) {const jobs=[...this.jobs.values()];this.jobs.clear();for(const job of jobs)job();await controller.queue;await new Promise(resolve=>setImmediate(resolve));}
}
export function fixture({github=new FakeGitHub(), store=new MemoryState(),host=new FakeHost(), cfg=config}={}) {
  const clock=new ManualClock();const controller=new ProjectController({config:cfg,github,store,host,clock});
  return {controller,github,store,host,clock};
}
export const start = f => f.controller.start({selectOwner:true});
export async function settle(f) {f.host.acknowledge();await f.controller.idle();}
export async function observe(f) {await f.controller.serial(()=>f.controller.observe(f.controller.abort.signal));}
export function deferred() {let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}

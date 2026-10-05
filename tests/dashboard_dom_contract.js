// Minimal rendering/event contract harness; not a browser or DOM-layout test.
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const fixture=JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
fixture.detail.tasks[0].title='<img src=x onerror=alert(1)>';
const elements={};
function element(id){return elements[id] ||= {id,innerHTML:'',textContent:'',dataset:{},listeners:{},open:false,setAttribute(k,v){this[k]=v},addEventListener(k,fn){this.listeners[k]=fn},focus(){document.activeElement=this},setSelectionRange(){},showModal(){this.open=true},close(){this.open=false;if(this.listeners.close)this.listeners.close()},getBoundingClientRect(){return{left:900,right:1440,top:0,bottom:1000}}}}
const document={getElementById:element,documentElement:{dataset:{}},querySelectorAll(){return[]},addEventListener(){},activeElement:null};
let fail=false;
const context={document,console,location:{origin:'http://127.0.0.1:18766',search:''},history:{replaceState(){}},localStorage:{getItem(){return null},setItem(){}},matchMedia(){return{matches:false}},URL,URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval(){},fetch:async path=>({ok:!fail,status:fail?500:200,json:async()=>path==='/api/projects'?fixture.catalog:fixture.detail}),Intl,Date};
vm.runInNewContext(fs.readFileSync('web/app.js','utf8'),context);
const settle=()=>new Promise(resolve=>setTimeout(resolve,10));
(async()=>{
 await settle();assert(element('content').innerHTML.includes('executor-card'));assert(element('task-rows').innerHTML.includes('&lt;img'));assert(!element('task-rows').innerHTML.includes('<img'));
 const counts={active:1,waiting:1,blocked:1,completed:2,all:5};
 for(const [filter,count] of Object.entries(counts)){
  element('content').listeners.click({target:{closest(selector){return selector==='[data-filter]'?{dataset:{filter}}:null}}});
  assert.equal((element('task-rows').innerHTML.match(/class="task-row"/g)||[]).length,count,filter);
 }
 element('content').listeners.input({target:{id:'task-search',value:'fixture-job-0'}});assert.equal((element('task-rows').innerHTML.match(/class="task-row"/g)||[]).length,1);
 element('content').listeners.click({target:{closest(selector){return selector==='[data-executor]'?{dataset:{executor:'fixture-job-0'}}:null}}});
 assert(element('executor-dialog').open);assert(element('drawer-content').innerHTML.includes('通过'));assert(element('drawer-content').innerHTML.includes('synthetic-session-0'));
 element('close-drawer').listeners.click();assert(!element('executor-dialog').open);
 element('theme-toggle').listeners.click();assert.equal(document.documentElement.dataset.theme,'dark');
 fail=true;await element('refresh').listeners.click();await settle();assert(element('notice').innerHTML.includes('HTTP 500'));assert(element('content').innerHTML.includes('executor-card'));
 console.log('PASS minimal JS contracts: XSS escaping, real backend status filters, executor-ID search, drawer receipt checks, close, theme, error retention. Not browser rendering.');
})().catch(error=>{console.error(error);process.exitCode=1});

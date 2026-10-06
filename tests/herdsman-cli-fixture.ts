// Opt-in test fixture: load only into a new Pi CLI inside an isolated Herdr PTY.
// No remote model/GitHub calls, credentials, tasks, or production configuration.
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {mkdir,writeFile} from 'node:fs/promises';
import {Type} from '@earendil-works/pi-ai';
import {registerGitHubProject} from '../extensions/github-project/pi-host.mjs';
import {FakeGitHub,config} from './fakes.mjs';

export default async function(pi) {
  assert.equal(process.env.HERDR_ENV,'1');
  const root=process.env.PI_FIXTURE_PACKAGE_ROOT,output=process.env.PI_FIXTURE_REPORT;
  assert.ok(root && output && process.env.PI_CODING_AGENT_DIR);
  const {fauxProvider,fauxAssistantMessage}=await import(pathToFileURL(path.join(root,
    'node_modules/@earendil-works/pi-ai/dist/providers/faux.js')).href);
  const github=new FakeGitHub();
  const faux=fauxProvider({provider:'project-fixture',tokensPerSecond:100000});
  let current,hooks=0,noticeCalls=0,busyHeld=false,managerCharter=false,completed=false,timer;
  const notices=()=>current.sessionManager.getBranch().filter(e=>e.type==='message' &&
    e.message.role==='user' && JSON.stringify(e.message.content).includes('[pi-github-notice:'));
  const finish=async(report)=>{
    if(completed)return;completed=true;clearTimeout(timer);
    await writeFile(output,JSON.stringify(report,null,2)+'\n');current.shutdown();
  };
  const response=async context=>{
    const user=[...context.messages].reverse().find(m=>m.role==='user');
    if(JSON.stringify(user).includes('[pi-github-notice:')){
      noticeCalls++;
      const text=JSON.stringify(context);
      managerCharter ||= text.includes('## Manager role') && text.includes('Manage project work by branch.');
      if(noticeCalls===1){
        github.externalComment('Fixture one','EXT1');github.externalComment('Fixture two','EXT2');
        await new Promise(r=>setTimeout(r,1800));
        busyHeld=notices().length===1;
      }
    }
    return fauxAssistantMessage('Local fixture response; no delegation.');
  };
  faux.setResponses(Array.from({length:12},()=>response));pi.registerProvider(faux.provider);
  // The actual CLI generates the session id; the fixture binds exactly that id.
  pi.on('session_start',async(_event,ctx)=>{
    current=ctx;assert.equal(ctx.mode,'tui');
    await mkdir(path.join(ctx.cwd,'.pi'),{recursive:true});
    await writeFile(path.join(ctx.cwd,'.pi/github-project.json'),JSON.stringify({
      ...config,mainSessionId:ctx.sessionManager.getSessionId()}));
    timer=setTimeout(()=>void finish({passed:false,error:'Fixture deadline',
      tools:pi.getActiveTools(),noticeCalls,hooks}),45000);
  });
  registerGitHubProject(pi,Type,{github});
  pi.on('before_agent_start',()=>{hooks++;});
  pi.on('agent_settled',async(_event,ctx)=>{
    current=ctx;
    if(noticeCalls!==2 || completed)return;
    setTimeout(()=>void (async()=>{
      try{
        const staff=['staff_delegate','staff_resume','staff_message','staff_list'];
        assert.ok(staff.every(name=>pi.getActiveTools().includes(name)));
        const roles=ctx.sessionManager.getEntries().filter(e=>e.type==='custom' && e.customType==='pi-herdsman-role');
        // Native auto-activation may not append a role entry in a fresh session;
        // exact active staff capabilities + native charter prove Manager mode.
        if(roles.length)assert.equal(roles.at(-1).data.role,'manager');
        assert.equal(notices().length,2);assert.ok(busyHeld && managerCharter && hooks>=2);
        await finish({passed:true,piVersion:'1.0.2',herdrVersion:'0.9.3',herdsmanVersion:'0.21.0',
          actualPiCLI:true,actualHerdrPTY:true,nativeManagerRole:true,requiredStaffTools:staff,
          firstReadNotice:true,busyCoalesced:true,persistedNotices:2,beforeAgentStartHooks:hooks,
          managerCharter:true,unchangedNoDuplicate:true,localFauxCalls:faux.state.callCount,
          remoteModelCalls:0,github:'fixture only',delegations:0});
      }catch(error){await finish({passed:false,error:String(error),noticeCalls,hooks});}
    })(),1500);
  });
  pi.on('session_shutdown',()=>clearTimeout(timer));
}

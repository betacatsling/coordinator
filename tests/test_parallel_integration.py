import json
import uuid
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from project_acpx import Coordinator
from github_project_inputs import normalize_project
from github_board import select_tasks,assert_claimable

class ParallelIntegrationTests(unittest.TestCase):
    def test_two_fixture_workers_overlap_with_serial_coordinator_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';repo.mkdir()
            for args in [['init'],['config','user.name','Fixture'],['config','user.email','fixture@example.invalid']]:subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
            (repo/'base.txt').write_text('base');subprocess.run(['git','-C',str(repo),'add','base.txt'],check=True);subprocess.run(['git','-C',str(repo),'commit','-m','base'],check=True,capture_output=True)
            project={'id':'P','items':{'nodes':[{'id':'ITEM-'+name,'content':{'__typename':'Issue','id':name,'body':'Task-'+name,'repository':{'nameWithOwner':'u/r'},'author':{'login':'u'},'comments':{'nodes':[]}}} for name in ['A','B']]}}
            source=root/'source.json';source.write_text(json.dumps(project));runtime=root/'runtime';runtime.write_text('fixture')
            c={'workspace':str(repo),'project_node_id':'P','repository':'u/r','user_login':'u','source':{'type':'fixture','path':str(source)},'executor':{'enabled':True,'isolate_worktree':True,'server':str(runtime),'bridge_state_root':str(root/'bridge'),'checks':[]},**{k:str(runtime) for k in ['node','acpx','adapter','codex','html_cli']}}
            config=root/'config.json';config.write_text(json.dumps(c));obj=Coordinator(config);obj.state['binding']={'provider_thread_id':'COORDINATOR'};obj.verify=lambda:None;obj.publish=lambda *_:{'local_path':'fixture','url':None}
            stats={'active':0,'max':0,'model_active':0,'model_max':0};lock=threading.Lock();barrier=threading.Barrier(2)
            def model(prompt):
                with lock:stats['model_active']+=1;stats['model_max']=max(stats['model_max'],stats['model_active'])
                time.sleep(.03)
                with lock:stats['model_active']-=1
                if 'Program observations:' in prompt:return json.dumps({'accepted':True,'summary':'accepted','blockers':[]})
                name='A' if '"instructions": "Task-A"' in prompt else 'B'
                return json.dumps({'assignment':'Task-'+name,'owned_paths':[name+'.txt'],'depends_on':[],'resources':[]})
            obj._coordinate=model
            def executor(prompt,config,receipt,node,on_session=None):
                name=config['owned_paths'][0][0];thread=str(uuid.UUID(int=1 if name=='A' else 2))
                with lock:stats['active']+=1;stats['max']=max(stats['max'],stats['active'])
                if on_session:on_session({'thread_id':thread,'job_id':name,'workspace':config['cwd'],'bridge_state_root':config['bridge_state_root']})
                barrier.wait(timeout=5);(Path(config['cwd'])/(name+'.txt')).write_text(name);time.sleep(.03)
                with lock:stats['active']-=1
                return {'status':'verified','thread_id':thread,'checks':[{'argv':['fixture-check'],'returncode':0}],'artifacts':{name+'.txt':{'content':name}}}
            try:
                with patch('mcp_executor.execute_assignment',side_effect=executor):obj.run(once=True)
                self.assertEqual(stats['max'],2);self.assertEqual(stats['model_max'],1);self.assertTrue(all(e['status']=='completed' for e in obj.state['queue']));self.assertEqual(len(obj.state['executor_sessions']),2);self.assertEqual(len({v['thread_id'] for v in obj.state['executor_sessions'].values()}),2)
            finally:obj.lock.close()
    def test_explicit_current_batch_can_dispatch_old_triage_snapshot_once(self):
        c={'project_node_id':'P','repository':'u/r','user_login':'u','board':{'view_id':'V','view_filter':'-类型:"项目跟踪"','status_field_id':'S','ready_option_id':'todo','ready_option_name':'待做','triage_option_id':'triage','triage_option_name':'待整理','type_field_id':'T','excluded_type_option_id':'tracking','excluded_type_option_name':'项目跟踪'}}
        p={'id':'P','views':{'nodes':[{'id':'V','filter':c['board']['view_filter'],'layout':'BOARD_LAYOUT'}]},'fields':{'nodes':[{'id':'S','options':[{'id':'todo','name':'待做'},{'id':'triage','name':'待整理'}]},{'id':'T','options':[{'id':'tracking','name':'项目跟踪'}]}]},'items':{'nodes':[{'id':'ITEM','fieldValues':{'nodes':[{'field':{'id':'S'},'optionId':'triage'}]},'content':{'__typename':'Issue','id':'I','body':'current task','author':{'login':'u'},'repository':{'nameWithOwner':'u/r'},'comments':{'nodes':[]}}}]}}
        tasks=normalize_project(p,'P','u',selected_repository='u/r');observations={};self.assertEqual(select_tasks(p,c,tasks,observations),[])
        c['manual_dispatch']={'id':'authorized-current-batch','tasks':{'I':tasks[0]['revision_hash']}};one=select_tasks(p,c,tasks,observations);assert_claimable(p,c,one[0]);two=select_tasks(p,c,tasks,observations);self.assertEqual(one[0]['dispatch_key'],two[0]['dispatch_key']);self.assertEqual(one[0]['manual_dispatch_id'],c['manual_dispatch']['id'])
        changed=dict(tasks[0],revision_hash='changed');self.assertEqual(select_tasks(p,c,[changed],observations),[])
        p['items']['nodes'][0]['fieldValues']['nodes'].append({'field':{'id':'T'},'optionId':'tracking'});self.assertEqual(select_tasks(p,c,tasks,observations),[])

if __name__=='__main__':unittest.main()

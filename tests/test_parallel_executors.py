import copy
import json
import uuid
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from parallel_executors import ScopeGate,overlaps
from project_acpx import Coordinator
from github_writeback import write_claim,write_executor_session
import test_github_backend as fixtures

class ParallelTests(unittest.TestCase):
    def test_disjoint_files_lease_together_and_parent_paths_conflict(self):
        g=ScopeGate();self.assertTrue(g.try_acquire('A',['a/x.md']));self.assertTrue(g.try_acquire('B',['b/y.md']))
        self.assertFalse(g.try_acquire('C',['a']));g.release('A');self.assertTrue(g.try_acquire('C',['a']))
        self.assertTrue(overlaps('a','a/z'));self.assertFalse(overlaps('a','ab'))
    def test_shared_resource_waits_without_serializing_unrelated_work(self):
        g=ScopeGate();self.assertTrue(g.try_acquire('A',['a'],['gpu0']));self.assertFalse(g.try_acquire('B',['b'],['gpu0']));self.assertTrue(g.try_acquire('C',['c'],['docs']))
        g.release('A');self.assertTrue(g.try_acquire('B',['b'],['gpu0']))
    def test_dependencies_and_resources_release_only_when_satisfied(self):
        obj=Coordinator.__new__(Coordinator);obj.scope_gate=ScopeGate();obj.scope_gate.try_acquire('held',['owned'])
        waiting={'task':{'issue_id':'B'},'status':'waiting_dependencies','depends_on':['A']}
        files={'task':{'issue_id':'C'},'status':'waiting_resources','prepared_plan':{'owned_paths':['owned'],'resources':[]}}
        obj.state={'queue':[{'task':{'issue_id':'A'},'status':'completed','acceptance':{'accepted':False}},waiting,files]};obj.release_waiting();self.assertEqual(waiting['status'],'waiting_dependencies');self.assertEqual(files['status'],'waiting_resources')
        obj.state['queue'][0]['acceptance']['accepted']=True;obj.scope_gate.release('held');obj.release_waiting();self.assertEqual(waiting['status'],'pending');self.assertEqual(files['status'],'pending')
    def test_executor_session_updates_existing_claim_once(self):
        f=fixtures.BackendTests();f.setUp();write_claim(f.c,f.task,f.project,f.gh,False)
        thread=str(uuid.UUID(int=1))
        preview=write_executor_session(f.c,f.task,f.project,thread,f.gh,True);self.assertEqual([o['operation'] for o in preview['operations']],['update_comment'])
        f.project['items']['nodes'][0]['content']['comments']['nodes'][0]['body']=preview['operations'][0]['body'];f.calls=[]
        again=write_executor_session(f.c,f.task,f.project,thread,f.gh,False);self.assertEqual(again['operations'],[]);self.assertFalse(any(q.startswith('mutation') for q,v in f.calls))
    def test_missing_claim_does_not_create_session_comment(self):
        f=fixtures.BackendTests();f.setUp()
        with self.assertRaises(ValueError):write_executor_session(f.c,f.task,f.project,str(uuid.UUID(int=1)),f.gh,False)
        self.assertFalse(any(q.startswith('mutation') for q,v in f.calls))

if __name__=='__main__':unittest.main()

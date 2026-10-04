import copy
import functools
import http.server
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from github_project_inputs import normalize_project
from github_writeback import write_result, is_result_comment
from issue_worktree import create, inspect, validate_paths, git
from project_acpx import Coordinator

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.c={'project_node_id':'P','repository':'u/r','user_login':'u','writeback':{'status':{'field_id':'F','accepted_option_id':'ready','accepted_option_name':'Review'}}}
        self.project={'id':'P','items':{'nodes':[{'id':'ITEM','fieldValues':{'nodes':[]},'content':{'__typename':'Issue','id':'I','body':'Fix code','author':{'login':'u'},'repository':{'nameWithOwner':'u/r'},'comments':{'nodes':[]}}}]}}
        self.task=normalize_project(self.project,'P','u',selected_repository='u/r')[0];self.calls=[]
    def gh(self,q,**v):
        self.calls.append((q,v))
        if 'viewer' in q:return {'viewer':{'login':'u'}}
        if 'fields(' in q:return {'node':{'fields':{'pageInfo':{'hasNextPage':False},'nodes':[{'id':'F','options':[{'id':'ready','name':'Review'}]}]}}}
        if 'addComment' in q:
            self.project['items']['nodes'][0]['content']['comments']['nodes'].append({'id':'C','body':v['body'],'author':{'login':'u'}})
            return {'addComment':{'commentEdge':{'node':{'id':'C'}}}}
        if 'updateProjectV2ItemFieldValue' in q:
            self.project['items']['nodes'][0]['fieldValues']['nodes']=[{'field':{'id':'F'},'optionId':v['option']}]
            return {'updateProjectV2ItemFieldValue':{'projectV2Item':{'id':'ITEM'}}}
        raise AssertionError('Unexpected API')
    def test_dryrun_and_retry_after_lost_receipt(self):
        r=write_result(self.c,self.task,self.project,'ok',{},True,self.gh,True)
        self.assertEqual(len(r['operations']),2);self.assertFalse(any(q.startswith('mutation') for q,v in self.calls))
        first=write_result(self.c,self.task,self.project,'ok',{},True,self.gh,False)
        self.assertEqual(first['comment_id'],'C');self.calls=[]
        again=write_result(self.c,self.task,self.project,'ok',{},True,self.gh,False)
        self.assertEqual(again['operations'],[]);self.assertFalse(any(q.startswith('mutation') for q,v in self.calls))
        comment=self.project['items']['nodes'][0]['content']['comments']['nodes'][0]
        self.assertTrue(is_result_comment(comment['body'],self.c,'I'))
        self.assertEqual(normalize_project(self.project,'P','u',['C'],'u/r')[0]['revision_hash'],self.task['revision_hash'])
    def test_scope_revision_author_and_unknown_status_refused(self):
        for change in ['project','repository','revision','author','option']:
            c=copy.deepcopy(self.c);p=copy.deepcopy(self.project);t=copy.deepcopy(self.task)
            if change=='project':p['id']='other'
            if change=='repository':p['items']['nodes'][0]['content']['repository']['nameWithOwner']='u/other'
            if change=='revision':p['items']['nodes'][0]['content']['body']='new input'
            if change=='author':c['user_login']='other'
            if change=='option':c['writeback']['status']['accepted_option_id']='unknown'
            self.calls=[]
            with self.assertRaises(ValueError):write_result(c,t,p,'ok',{},True,self.gh,False)
            self.assertFalse(any(q.startswith('mutation') for q,v in self.calls))
    def test_dirty_main_tree_preserved_and_scope_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';repo.mkdir();git(repo,'init');git(repo,'config','user.name','Fixture');git(repo,'config','user.email','fixture@example.invalid')
            (repo/'owned.py').write_text('x=1\n');git(repo,'add','owned.py');git(repo,'commit','-m','fixture')
            (repo/'owned.py').write_text('x=99 # main dirty\n');before=git(repo,'status','--porcelain')
            with self.assertRaises(ValueError):create(repo,self.task,root/'overlap-state',['owned.py'])
            work,head=create(repo,self.task,root/'state');self.assertEqual((work/'owned.py').read_text(),'x=1\n')
            (work/'owned.py').write_text('x=2\n');self.assertEqual(inspect(work,['owned.py']),['owned.py'])
            self.assertEqual(git(repo,'status','--porcelain'),before);self.assertIn('99',(repo/'owned.py').read_text())
            (work/'other.txt').write_text('bad')
            with self.assertRaises(ValueError):inspect(work,['owned.py'])
            with self.assertRaises(ValueError):create(repo,self.task,root/'state')
            for scope in [['.git'],['../escape'],['.'],['docs/.codex/foo']]:
                with self.assertRaises(ValueError):validate_paths(scope)
    def test_live_legacy_watcher_blocks_new_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'.project-delegation').mkdir()
            (root/'.project-delegation/state.json').write_text(json.dumps({'watcher_pid':os.getpid()}))
            obj=Coordinator.__new__(Coordinator);obj.workspace=root
            with self.assertRaisesRegex(RuntimeError,'Legacy watcher is alive'):obj.run(once=True)

    def test_report_base_url_on_loopback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'state';folder.mkdir();reports=root/'reports';reports.mkdir()
            handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(reports))
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler);threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                obj=Coordinator.__new__(Coordinator);obj.workspace=root;obj.folder=folder
                obj.config={'node':os.environ.get('PROJECT_DELEGATION_TEST_NODE',shutil.which('node')),'html_cli':os.environ.get('PROJECT_DELEGATION_TEST_HTML_CLI',str(Path.home()/'.codex/skills/answer-me-with-html/scripts/am.mjs')),'report_base_url':'http://127.0.0.1:'+str(server.server_port)}
                report=obj.publish({'task':self.task},'Fixture report')
                self.assertTrue(report['access_verified']);self.assertTrue(report['url'].startswith('http://127.0.0.1:'))
                self.assertTrue(Path(report['local_path']).is_file())
            finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()

import copy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from github_project_inputs import normalize_project
from github_writeback import write_result, write_claim, is_result_comment, is_workflow_comment
from issue_worktree import create, inspect, validate_paths, git

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
            comments=self.project['items']['nodes'][0]['content']['comments']['nodes']
            comment_id='C' if not comments else 'C'+str(len(comments)+1)
            comments.append({'id':comment_id,'body':v['body'],'author':{'login':'u'}})
            return {'addComment':{'commentEdge':{'node':{'id':comment_id}}}}
        if 'updateIssueComment' in q:
            next(c for c in self.project['items']['nodes'][0]['content']['comments']['nodes'] if c['id']==v['id'])['body']=v['body']
            return {'updateIssueComment':{'issueComment':{'id':v['id']}}}
        if 'updateProjectV2ItemFieldValue' in q:
            self.project['items']['nodes'][0]['fieldValues']['nodes']=[{'field':{'id':'F'},'optionId':v['option']}]
            return {'updateProjectV2ItemFieldValue':{'projectV2Item':{'id':'ITEM'}}}
        raise AssertionError('Unexpected API')
    def test_dryrun_and_retry_after_lost_receipt(self):
        write_claim(self.c,self.task,self.project,self.gh,False);self.calls=[]
        r=write_result(self.c,self.task,self.project,'ok',{},True,self.gh,True)
        self.assertEqual(len(r['operations']),2);self.assertFalse(any(q.startswith('mutation') for q,v in self.calls))
        first=write_result(self.c,self.task,self.project,'ok',{},True,self.gh,False)
        self.assertEqual(first['comment_id'],'C2');self.calls=[]
        again=write_result(self.c,self.task,self.project,'ok',{},True,self.gh,False)
        self.assertEqual(again['operations'],[]);self.assertFalse(any(q.startswith('mutation') for q,v in self.calls))
        comment=self.project['items']['nodes'][0]['content']['comments']['nodes'][-1]
        self.assertTrue(is_result_comment(comment['body'],self.c,'I'))
        self.assertEqual(normalize_project(self.project,'P','u',['C','C2'],'u/r')[0]['revision_hash'],self.task['revision_hash'])
    def test_scope_revision_author_and_unknown_status_refused(self):
        write_claim(self.c,self.task,self.project,self.gh,False)
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
    def test_claim_dryrun_retry_and_no_revision_feedback(self):
        self.c['writeback']['status'].update(claimed_option_id='ready',claimed_option_name='Review')
        preview=write_claim(self.c,self.task,self.project,self.gh,True)
        self.assertEqual([o['operation'] for o in preview['operations']],['add_comment','set_status','update_comment'])
        self.assertFalse(any(q.startswith('mutation') for q,v in self.calls))
        first=write_claim(self.c,self.task,self.project,self.gh,False)
        self.assertEqual(first['comment_id'],'C')
        comment=self.project['items']['nodes'][0]['content']['comments']['nodes'][0]
        self.assertIn('已领取',comment['body']);self.assertIn(self.task['revision_hash'][:12],comment['body'])
        self.assertTrue(is_workflow_comment(comment['body'],self.c,'I'))
        self.calls=[];again=write_claim(self.c,self.task,self.project,self.gh,False)
        self.assertEqual(again['operations'],[]);self.assertFalse(any(q.startswith('mutation') for q,v in self.calls))
        result_preview=write_result(self.c,self.task,self.project,'done',{},True,self.gh,True)
        self.assertEqual(result_preview['operations'][0]['operation'],'add_comment')
        # Workflow comments remain excluded even when local receipts were lost.
        comments = self.project['items']['nodes'][0]['content']['comments']['nodes']
        discovered = [c['id'] for c in comments if is_workflow_comment(c['body'], self.c, 'I')]
        self.assertEqual(discovered, ['C'])
        fresh = normalize_project(self.project, 'P', 'u', discovered, 'u/r')[0]
        self.assertEqual(fresh['revision_hash'], self.task['revision_hash'])

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


if __name__=='__main__':unittest.main()

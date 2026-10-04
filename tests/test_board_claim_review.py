"""Regression checks for fail-closed board scope and retry-safe claim writes."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from github_board import board_members, select_tasks
from github_project_inputs import normalize_project
from github_writeback import write_claim, marker_prefix


class BoardClaimReviewTests(unittest.TestCase):
    def setUp(self):
        self.config={'project_node_id':'P','repository':'u/r','user_login':'u','board':{
            'view_id':'V','view_filter':'-类型:"项目跟踪"','status_field_id':'S',
            'ready_option_id':'todo','ready_option_name':'待做','type_field_id':'T',
            'excluded_type_option_id':'tracking','excluded_type_option_name':'项目跟踪'},
            'writeback':{'status':{'field_id':'S','claimed_option_id':'doing','claimed_option_name':'进行中'}}}
        self.project={'id':'P','views':{'nodes':[{'id':'V','filter':'-类型:"项目跟踪"','layout':'BOARD_LAYOUT'}]},
            'fields':{'nodes':[{'id':'S','options':[{'id':'todo','name':'待做'},{'id':'doing','name':'进行中'}]},
                                {'id':'T','options':[{'id':'tracking','name':'项目跟踪'}]}]},
            'items':{'nodes':[{'id':'ITEM','fieldValues':{'nodes':[{'field':{'id':'S'},'optionId':'todo'},
               {'field':{'id':'T'},'optionId':'research'}]},'content':{'__typename':'Issue','id':'I',
               'body':'Implement bounded fix','author':{'login':'u'},'repository':{'nameWithOwner':'u/r'},
               'comments':{'nodes':[]}}}]}}
        self.task=normalize_project(self.project,'P','u',selected_repository='u/r')[0]
        self.task=select_tasks(self.project,self.config,[self.task],{})[0]
        self.calls=[]

    def query(self,q,**args):
        self.calls.append((q,args))
        if 'viewer' in q:return {'viewer':{'login':'u'}}
        if 'fields(' in q:return {'node':{'fields':dict(self.project['fields'],pageInfo={'hasNextPage':False})}}
        if 'updateProjectV2ItemFieldValue' in q:
            self.project['items']['nodes'][0]['fieldValues']['nodes'][0]['optionId']=args['option']
            return {'updateProjectV2ItemFieldValue':{'projectV2Item':{'id':'ITEM'}}}
        if 'addComment' in q:
            self.project['items']['nodes'][0]['content']['comments']['nodes'].append(
                {'id':'COMMENT','body':args['body'],'author':{'login':'u'}})
            return {'addComment':{'commentEdge':{'node':{'id':'COMMENT'}}}}
        raise AssertionError(q)

    def test_wrong_project_partial_pages_and_duplicate_issue_rejected(self):
        for invalid in ['project','items','views','fields','item_fields','duplicate']:
            p=copy.deepcopy(self.project)
            if invalid=='project':p['id']='other'
            elif invalid=='item_fields':p['items']['nodes'][0]['fieldValues']['pageInfo']={'hasNextPage':True}
            elif invalid=='duplicate':p['items']['nodes'].append(copy.deepcopy(p['items']['nodes'][0]))
            else:p[invalid]['pageInfo']={'hasNextPage':True}
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):board_members(p,self.config)

    def test_claim_direct_call_rechecks_ready_and_type_before_mutating(self):
        for field,option in [('S','triage'),('T','tracking')]:
            p=copy.deepcopy(self.project)
            next(v for v in p['items']['nodes'][0]['fieldValues']['nodes'] if v['field']['id']==field)['optionId']=option
            self.calls=[]
            with self.subTest(field=field),self.assertRaises(ValueError):write_claim(self.config,self.task,p,self.query,False)
            self.assertFalse(any(q.startswith('mutation') for q,args in self.calls))

    def test_lost_receipt_does_not_repost_or_regress_changed_status(self):
        first=write_claim(self.config,self.task,self.project,self.query,False)
        self.assertEqual(first['comment_id'],'COMMENT')
        self.assertEqual(self.project['items']['nodes'][0]['fieldValues']['nodes'][0]['optionId'],'doing')
        self.calls=[]
        second=write_claim(self.config,self.task,self.project,self.query,False)
        self.assertTrue(second['recovered']);self.assertEqual(second['operations'],[])
        self.assertFalse(any(q.startswith('mutation') for q,args in self.calls))

    def test_other_authors_marker_is_not_owned_and_cannot_hide_input(self):
        issue=self.project['items']['nodes'][0]['content']
        issue['comments']['nodes'].append({'id':'OTHER','author':{'login':'other'},
            'body':marker_prefix(self.config,'I','claim')+self.task['dispatch_key']+' -->'})
        preview=write_claim(self.config,self.task,self.project,self.query,True)
        self.assertEqual([op['operation'] for op in preview['operations']],['set_status','add_comment'])
        self.assertFalse(any(q.startswith('mutation') for q,args in self.calls))

    def test_non_issue_and_other_repository_never_selected(self):
        for kind,repo in [('PullRequest','u/r'),('Issue','u/else')]:
            p=copy.deepcopy(self.project);p['items']['nodes'][0]['content'].update(__typename=kind,repository={'nameWithOwner':repo})
            self.assertEqual(select_tasks(p,self.config,[self.task],{}),[])

if __name__=='__main__':unittest.main()

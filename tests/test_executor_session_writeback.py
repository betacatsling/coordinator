import uuid
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from github_writeback import write_claim,write_executor_session
import test_github_backend as fixtures

class ExecutorSessionWritebackTests(unittest.TestCase):
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

import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from project_acpx import Coordinator

class OwnershipTests(unittest.TestCase):
    def config(self,root,state=None,ledger=None,command=None):
        runtime=root/'runtime';runtime.write_text('fixture')
        config={'workspace':str(root),'project_node_id':'P','repository':'u/r','user_login':'u',**{k:str(runtime) for k in ['node','acpx','adapter','codex','html_cli']}}
        if state:config['state_directory']=str(state)
        if ledger:config['provider_ledger']=str(ledger)
        if command:config['agent_command']=command
        path=root/('config-'+str(len(list(root.glob('config-*'))))+'.json');path.write_text(json.dumps(config));return path
    def test_one_lock_across_registered_state_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);first=Coordinator(self.config(root))
            try:
                with self.assertRaises(BlockingIOError):Coordinator(self.config(root,root/'.project-delegation/registered/candidate'))
            finally:first.lock.close()
            second=Coordinator(self.config(root,root/'.project-delegation/registered/candidate'));second.lock.close()
    def test_scope_escape_and_arbitrary_guard_command_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaises(ValueError):Coordinator(self.config(root,root/'outside'))
            with self.assertRaises(ValueError):Coordinator(self.config(root,ledger=root/'provider.json'))
            with self.assertRaises(ValueError):Coordinator(self.config(root,command='arbitrary command'))

if __name__=='__main__':unittest.main()

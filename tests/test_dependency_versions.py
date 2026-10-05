import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from project_acpx import Coordinator

class DependencyVersionTests(unittest.TestCase):
    def test_historical_acceptance_cannot_satisfy_current_version(self):
        obj=Coordinator.__new__(Coordinator)
        obj.state={'queue':[{'task':{'issue_id':'A','revision_hash':'old'},'status':'completed','acceptance':{'accepted':True}}, {'task':{'issue_id':'A','revision_hash':'new'},'status':'pending'}]}
        plan={'depends_on':['A']}
        data,waiting=obj.dependency_inputs({'issue_id':'B'},plan)
        self.assertEqual(waiting,['A']);self.assertEqual(data,[])
        self.assertEqual(plan['dependency_versions'],{'A':'new'})
    def test_revised_dependency_requires_replanning(self):
        obj=Coordinator.__new__(Coordinator);obj.state={'queue':[{'task':{'issue_id':'A','revision_hash':'new'},'status':'pending'}]}
        with self.assertRaisesRegex(ValueError,'version changed'):
            obj.dependency_inputs({'issue_id':'B'},{'depends_on':['A'],'dependency_versions':{'A':'old'}})
    def test_verified_upstream_artifacts_are_passed_to_downstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'receipt.json';path.write_text(json.dumps({'status':'verified','artifacts':{'out.md':{'content':'accepted artifact','sha256':'hash'}},'checks':[{'returncode':0}]}))
            obj=Coordinator.__new__(Coordinator);obj.state={'queue':[{'task':{'issue_id':'A','revision_hash':'r'},'status':'completed','acceptance':{'accepted':True},'executor_receipt':str(path)}]}
            data,waiting=obj.dependency_inputs({'issue_id':'B'},{'depends_on':['A']})
            self.assertFalse(waiting);self.assertEqual(data[0]['artifacts']['out.md']['content'],'accepted artifact')
    def test_missing_artifacts_do_not_count_as_dependency_success(self):
        obj=Coordinator.__new__(Coordinator);obj.state={'queue':[{'task':{'issue_id':'A','revision_hash':'r'},'status':'completed','acceptance':{'accepted':True}}]}
        with self.assertRaises(ValueError):obj.dependency_inputs({'issue_id':'B'},{'depends_on':['A']})

if __name__=='__main__':unittest.main()

import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from app_server_client import turn_result

class TurnResultTests(unittest.TestCase):
    def test_match_actual_user_message_not_unrelated_result(self):
        t={'turns':[{'status':'completed','items':[{'type':'agentMessage','text':'marker'}]}]}
        self.assertIsNone(turn_result(t,'marker'))
        t['turns'][0]['items'].insert(0,{'type':'userMessage','content':[{'type':'text','text':'marker'}]})
        self.assertEqual(turn_result(t,'marker'),'marker')
    def test_duplicate_and_failed_turns_refused(self):
        turn={'status':'failed','items':[{'type':'userMessage','content':[{'type':'text','text':'x'}]}]}
        with self.assertRaises(RuntimeError):turn_result({'turns':[turn]},'x')
        with self.assertRaises(RuntimeError):turn_result({'turns':[turn,turn]},'x')

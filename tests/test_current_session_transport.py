import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from app_server_client import turn_result,register_request
from project_acpx import Coordinator,CoordinationPending

class FakeClient:
    submitted=[];result=None;state='idle'
    def __init__(self,*_):pass
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def thread(self,identity,workspace,turns=False):
        if self.state=='notLoaded':raise RuntimeError('not loaded')
        value={'id':identity,'cwd':str(workspace),'status':{'type':self.state}}
        if turns and self.submitted:
            text=self.submitted[-1]['input'][0]['text']
            value['turns']=[{'id':'T','status':'completed','items':[{'type':'userMessage','content':[{'type':'text','text':text}]},{'type':'agentMessage','text':'reply','phase':'final_answer'}]}]
        return value
    def request(self,method,params):
        assert method=='thread/queue/add'
        self.submitted.append(params)
        return {'queuedSubmission':{'id':'Q'}}

class CurrentSessionTests(unittest.TestCase):
    def setUp(self):FakeClient.submitted=[];FakeClient.state='idle'
    def test_match_actual_user_message_not_unrelated_result(self):
        t={'turns':[{'status':'completed','items':[{'type':'agentMessage','text':'marker'}]}]}
        self.assertIsNone(turn_result(t,'marker'))
        t['turns'][0]['items'].insert(0,{'type':'userMessage','content':[{'type':'text','text':'marker'}]})
        self.assertEqual(turn_result(t,'marker'),'marker')
    def test_duplicate_and_failed_turns_refused(self):
        turn={'status':'failed','items':[{'type':'userMessage','content':[{'type':'text','text':'x'}]}]}
        with self.assertRaises(RuntimeError):turn_result({'turns':[turn]},'x')
        with self.assertRaises(RuntimeError):turn_result({'turns':[turn,turn]},'x')
    def test_same_controller_consumes_registration_even_when_ui_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'enrollments';folder.mkdir()
            config=root/'config.json';config.write_text(json.dumps({'workspace':tmp,'codex':'unused','app_server_socket':'socket'}))
            receipt={'provider_thread_id':'new','identity_source':'runtime:CODEX_THREAD_ID','scope':{'workspace':tmp,'repository':'r','project_node_id':'P','user_login':'u'}}
            FakeClient.state='active'
            path,_=register_request(config,folder/'new.json',receipt,'old',FakeClient)
            obj=Coordinator.__new__(Coordinator);obj.folder=root;obj.workspace=root;obj.active={};obj.state={'binding':{'provider_thread_id':'old'},'queue':[{'status':'baseline'}]};obj.identity=dict(receipt['scope']);obj.save=lambda:None
            with patch('app_server_client.AppServer',FakeClient):self.assertTrue(obj.apply_binding_request())
            self.assertEqual(obj.state['binding']['provider_thread_id'],'new');self.assertEqual(obj.state['queue'],[{'status':'baseline'}])
            self.assertEqual(json.loads(path.read_text())['status'],'adopted')
            self.assertEqual(FakeClient.submitted,[])
    def test_queue_dispatch_returns_same_thread_result(self):
        obj=Coordinator.__new__(Coordinator);obj.workspace=Path('/tmp');obj.config={};obj.state={'binding':{'transport':'app_server','provider_thread_id':'real','socket_path':'socket'}};obj.save=lambda:None
        with patch('app_server_client.AppServer',FakeClient):self.assertEqual(obj.queue_coordinate('plan'),'reply')
        self.assertEqual(FakeClient.submitted[0]['threadId'],'real');self.assertNotIn('coordinator_request',obj.state)
    def test_unknown_submission_not_resent(self):
        import hashlib
        obj=Coordinator.__new__(Coordinator);obj.workspace=Path('/tmp');obj.config={'timeout':0};obj.state={'binding':{'provider_thread_id':'real','socket_path':'socket'},'coordinator_request':{'id':'id','digest':hashlib.sha256(b'plan').hexdigest(),'text':'original','status':'submitting'}};obj.save=lambda:None
        with patch('app_server_client.AppServer',FakeClient):
            with self.assertRaises(CoordinationPending):obj.queue_coordinate('plan')
        self.assertEqual(FakeClient.submitted,[]);self.assertEqual(obj.state['coordinator_request']['status'],'submitting')
    def test_unloaded_candidate_does_not_write_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);c=root/'config.json';c.write_text(json.dumps({'workspace':tmp,'codex':'unused','app_server_socket':'socket'}));FakeClient.state='notLoaded'
            with self.assertRaises(RuntimeError):register_request(c,root/'x.json',{'provider_thread_id':'x'},None,FakeClient)
            self.assertFalse((root/'x-request.json').exists())

class RecoveryTests(unittest.TestCase):
    def object(self):
        obj=Coordinator.__new__(Coordinator);obj.workspace=Path('/tmp');obj.config={'timeout':0};obj.active={}
        obj.state={'binding':{'transport':'app_server','provider_thread_id':'real','socket_path':'socket'},'queue':[{'status':'waiting_coordinator'}]};obj.save=lambda:None
        return obj
    def setUp(self):FakeClient.submitted=[];FakeClient.state='idle'
    def test_lost_ack_recovers_late_result_and_releases_task(self):
        obj=self.object()
        class LostAck(FakeClient):
            def request(self,method,params):
                FakeClient.submitted.append(params);raise OSError('lost acknowledgement')
        with patch('app_server_client.AppServer',LostAck):
            with self.assertRaises(CoordinationPending):obj.queue_coordinate('plan')
        self.assertEqual(obj.state['coordinator_request']['status'],'submitting')
        with patch('app_server_client.AppServer',FakeClient):obj.recover_queued_coordination()
        self.assertEqual(obj.state['queue'][0]['status'],'pending');self.assertNotIn('coordinator_request',obj.state)
        with patch('app_server_client.AppServer',FakeClient):self.assertEqual(obj.queue_coordinate('plan'),'reply')
        self.assertEqual(len(FakeClient.submitted),1)
    def test_terminal_failure_does_not_freeze_all_future_work(self):
        obj=self.object()
        with patch('app_server_client.AppServer',FakeClient):
            with self.assertRaises(CoordinationPending):obj.queue_coordinate('plan')
        class Failed(FakeClient):
            def thread(self,*args,**kwargs):
                value=super().thread(*args,**kwargs)
                if value.get('turns'):value['turns'][0]['status']='failed'
                return value
        with patch('app_server_client.AppServer',Failed):obj.recover_queued_coordination()
        self.assertNotIn('coordinator_request',obj.state)
        self.assertEqual(obj.state['queue'][0]['status'],'pending')
        with self.assertRaises(RuntimeError):obj.queue_coordinate('plan')
        obj.config['timeout']=1
        with patch('app_server_client.AppServer',FakeClient):self.assertEqual(obj.queue_coordinate('next task'),'reply')
    def test_completed_operation_key_survives_changed_dynamic_prompt(self):
        obj=self.object();obj.config['timeout']=1;obj._request_key='issue:version:plan'
        with patch('app_server_client.AppServer',FakeClient):
            self.assertEqual(obj.queue_coordinate('first snapshot'),'reply')
            self.assertEqual(obj.queue_coordinate('updated peer snapshot'),'reply')
        self.assertEqual(len(FakeClient.submitted),1)
    def test_persistent_running_task_blocks_handoff_before_any_connection(self):
        obj=self.object();obj.state['queue']=[{'status':'running'}]
        self.assertFalse(obj.apply_binding_request())
        obj.state['queue']=[{'status':'blocked','recovery_required':True}]
        self.assertFalse(obj.apply_binding_request())
    def test_corrupt_registration_is_reported_without_throwing(self):
        obj=self.object()
        with tempfile.TemporaryDirectory() as tmp:
            obj.folder=Path(tmp);(obj.folder/'enrollments').mkdir();(obj.folder/'enrollments/x-request.json').write_text('{bad')
            self.assertFalse(obj.apply_binding_request());self.assertIn('Unreadable',obj.state['binding_error'])

if __name__=='__main__':unittest.main()

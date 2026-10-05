import json
from pathlib import Path
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dashboard_launcher as launcher


class DashboardLauncherTests(unittest.TestCase):
    def setUp(self):
        platform = patch.object(launcher.sys, 'platform', 'linux')
        platform.start()
        self.addCleanup(platform.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scope = {'workspace': str(self.root), 'repository': 'owner/repo',
                      'project_node_id': 'P_123', 'user_login': 'owner'}
        self.folder = self.root / '.project-delegation/runtime'
        self.folder.mkdir(parents=True)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(self.scope))
        self.state = {'port': 18766, 'project_id': launcher.project_id(self.scope), 'instance': 'fixture', 'owner': 'owner-thread',
                      'config_signature': launcher.config_signature(self.scope)}
        (self.folder / 'dashboard.json').write_text(json.dumps(self.state))
        self.env = {'DISPLAY': ':0'}

    def launch(self, **kwargs):
        return launcher.launch_dashboard(self.config, self.scope, 'owner-thread', environment=self.env, **kwargs)

    def test_desktop_detection_respects_platform_and_remote_environment(self):
        self.assertTrue(launcher.local_browser_available({'WAYLAND_DISPLAY': 'wayland-0'}))
        self.assertFalse(launcher.local_browser_available({}))
        for key in ('SSH_CONNECTION', 'SSH_CLIENT', 'SSH_TTY', 'CI'):
            self.assertFalse(launcher.local_browser_available({'DISPLAY': ':0', key: 'fixture'}))
        with patch.object(launcher.sys, 'platform', 'win32'):
            self.assertTrue(launcher.local_browser_available({'SESSIONNAME': 'Console'}))
            self.assertFalse(launcher.local_browser_available({'SESSIONNAME': 'Services'}))
            self.assertFalse(launcher.local_browser_available({}))

    @patch.object(launcher.subprocess, 'run')
    def test_macos_requires_a_gui_session(self, run):
        with patch.object(launcher.sys, 'platform', 'darwin'), patch.object(launcher.os, 'getuid', return_value=501, create=True):
            run.return_value.returncode = 0
            self.assertTrue(launcher.local_browser_available({}))
            self.assertEqual(run.call_args.args[0], ['/bin/launchctl', 'print', 'gui/501'])
            run.return_value.returncode = 1
            self.assertFalse(launcher.local_browser_available({}))
            run.side_effect = OSError('unavailable')
            self.assertFalse(launcher.local_browser_available({}))
            run.side_effect = launcher.subprocess.TimeoutExpired('launchctl', 1)
            self.assertFalse(launcher.local_browser_available({}))

    @patch.object(launcher.webbrowser, 'open', return_value=True)
    @patch.object(launcher, 'healthy', return_value=True)
    @patch.object(launcher.subprocess, 'Popen')
    def test_reuses_and_opens_only_once(self, process, health, browser):
        result = self.launch()
        self.assertTrue(result['opened'])
        self.assertFalse(result['server_started'])
        self.assertIn('?project=' + self.state['project_id'], result['dashboard_url'])
        self.assertFalse(self.launch()['opened'])
        browser.assert_called_once()
        process.assert_not_called()

    @patch.object(launcher.webbrowser, 'open', return_value=True)
    @patch.object(launcher, 'healthy', return_value=True)
    @patch.object(launcher.subprocess, 'Popen')
    def test_concurrent_initialization_opens_once(self, process, health, browser):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.launch(), range(2)))
        self.assertEqual(sum(result['opened'] for result in results), 1)
        browser.assert_called_once()
        process.assert_not_called()

    @patch.object(launcher.webbrowser, 'open')
    @patch.object(launcher, 'healthy', return_value=True)
    def test_ssh_and_headless_never_open_browser(self, health, browser):
        for env in ({}, {'DISPLAY': ':0', 'SSH_CONNECTION': 'fixture'}):
            self.env = env
            result = self.launch()
            self.assertFalse(result['opened'])
            self.assertTrue(result['remote_access_required'])
            self.assertIsNotNone(result['dashboard_url'])
        browser.assert_not_called()

    @patch.object(launcher.webbrowser, 'open')
    @patch.object(launcher, 'healthy', return_value=True)
    def test_opt_out(self, health, browser):
        self.assertFalse(self.launch(auto_open=False)['opened'])
        browser.assert_not_called()

    @patch.object(launcher.webbrowser, 'open')
    @patch.object(launcher, 'healthy', side_effect=[False, True])
    @patch.object(launcher.subprocess, 'Popen')
    def test_opt_out_still_starts_server(self, process, health, browser):
        process.return_value.pid = 12345
        result = self.launch(auto_open=False)
        self.assertTrue(result['server_started'])
        self.assertIsNotNone(result['dashboard_url'])
        self.assertFalse(result['opened'])
        process.assert_called_once()
        browser.assert_not_called()

    @patch.object(launcher.webbrowser, 'open', return_value=False)
    @patch.object(launcher, 'healthy', return_value=True)
    def test_failed_browser_request_is_truthful(self, health, browser):
        result = self.launch()
        self.assertFalse(result['opened'])
        self.assertIn('browser', result['dashboard_warning'])
        self.assertNotIn('opened_for', launcher.read_state(self.folder / 'dashboard.json'))

    @patch.object(launcher, 'healthy', return_value=False)
    @patch.object(launcher.subprocess, 'Popen', side_effect=OSError('fixture'))
    def test_start_failure_nonfatal(self, process, health):
        result = self.launch()
        self.assertFalse(result['server_started'])
        self.assertFalse(result['opened'])
        self.assertIsNone(result['dashboard_url'])
        self.assertIn('dashboard_warning', result)

    @patch.object(launcher.webbrowser, 'open', return_value=True)
    @patch.object(launcher, 'healthy', side_effect=[False, True])
    @patch.object(launcher.subprocess, 'Popen')
    def test_starts_process_then_verifies(self, process, health, browser):
        process.return_value.pid = 12345
        result = self.launch()
        self.assertTrue(result['server_started'])
        self.assertTrue(result['opened'])
        args, options = process.call_args
        self.assertIn('--serve', args[0])
        self.assertEqual(options['stdin'], launcher.subprocess.DEVNULL)
        self.assertNotIn('shell', options)

    @patch.object(launcher, 'process_alive', return_value=True)
    @patch.object(launcher, 'healthy', return_value=False)
    @patch.object(launcher.subprocess, 'Popen')
    def test_pending_start_never_duplicates_process(self, process, health, alive):
        (self.folder / 'dashboard-start.json').write_text(json.dumps({'project_id': self.state['project_id'], 'pid': 12345}))
        self.assertIn('dashboard_warning', self.launch())
        process.assert_not_called()

    @patch.object(launcher.http.client, 'HTTPConnection')
    def test_health_verifies_service_scope_instance(self, connection):
        response = connection.return_value.getresponse.return_value
        response.status = 200
        data = {'service': launcher.SERVICE, 'project_ids': [self.state['project_id']], 'instance': 'fixture'}
        for change, expected in (({}, True), ({'service': 'other'}, False), ({'project_ids': ['other']}, False), ({'instance': 'stale'}, False)):
            response.read.return_value = json.dumps(dict(data, **change)).encode()
            self.assertEqual(launcher.healthy(self.state, self.state['project_id']), expected)
        self.assertFalse(launcher.healthy(dict(self.state, port=True), self.state['project_id']))
        self.assertFalse(launcher.healthy(self.state, 'different-project'))

    @patch.object(launcher, 'healthy', return_value=True)
    @patch.object(launcher, 'process_alive', side_effect=[True, False])
    def test_stop_is_instance_bound_and_allows_changed_non_scope_config(self, alive, health):
        self.state['pid'] = 12345
        (self.folder / 'dashboard.json').write_text(json.dumps(self.state))
        self.config.write_text(json.dumps(dict(self.scope, name='new display name')))
        result = launcher.stop_dashboard(self.config, self.scope, 'owner-thread')
        self.assertTrue(result['service_stopped'])
        request = launcher.read_state(self.folder / 'dashboard-stop.json')
        self.assertEqual(request, {'instance': 'fixture', 'owner': 'owner-thread'})

    @patch.object(launcher, 'healthy', return_value=True)
    @patch.object(launcher, 'process_alive', return_value=True)
    def test_stop_refuses_another_owner(self, alive, health):
        self.state['pid'] = 12345
        (self.folder / 'dashboard.json').write_text(json.dumps(self.state))
        with self.assertRaisesRegex(RuntimeError, 'refusing to stop'):
            launcher.stop_dashboard(self.config, self.scope, 'different-owner')
        self.assertFalse((self.folder / 'dashboard-stop.json').exists())

    @patch.object(launcher, 'healthy', return_value=False)
    @patch.object(launcher, 'process_alive', return_value=True)
    @patch.object(launcher.subprocess, 'Popen')
    def test_live_unhealthy_service_never_spawns_duplicate(self, process, alive, health):
        self.state['pid'] = 12345
        (self.folder / 'dashboard.json').write_text(json.dumps(self.state))
        self.assertIn('no duplicate', self.launch()['dashboard_warning'])
        process.assert_not_called()

    @patch.object(launcher.webbrowser, 'open', return_value=False)
    @patch.object(launcher, 'healthy', side_effect=[False, True])
    @patch.object(launcher, 'process_alive', return_value=False)
    @patch.object(launcher.subprocess, 'Popen')
    def test_dead_service_metadata_can_be_replaced_without_resetting_history(self, process, alive, health, browser):
        self.state.update(pid=12345, config_signature='old-config')
        (self.folder / 'dashboard.json').write_text(json.dumps(self.state))
        history = self.folder / 'notifier.json'
        history.write_text('{"saved": "history"}')
        process.return_value.pid = 54321
        result = self.launch()
        self.assertTrue(result['server_started'])
        self.assertEqual(history.read_text(), '{"saved": "history"}')
        process.assert_called_once()

    @patch.object(launcher, 'healthy', return_value=False)
    @patch.object(launcher.subprocess, 'Popen')
    def test_manual_watcher_lock_blocks_unified_duplicate(self, process, health):
        with (self.folder / 'notifier.lock').open('a+b') as lock:
            launcher.acquire_lock(lock, blocking=False)
            self.assertIn('existing watcher', self.launch()['dashboard_warning'])
        process.assert_not_called()

    @patch('web_dashboard.make_server')
    def test_serve_has_lifetime_lock(self, make_server):
        with (self.folder / 'project-service.lock').open('a+b') as lock:
            launcher.acquire_lock(lock, blocking=False)
            with self.assertRaises(BlockingIOError):
                launcher.serve(self.config, self.folder / 'dashboard.json')
        make_server.assert_not_called()

    @patch('board_notifier.BoardNotifier')
    @patch('web_dashboard.make_server')
    def test_service_owns_http_and_watcher_thread(self, make_server, notifier_class):
        server = Mock(server_port=54321, instance='unified')
        server.dashboard.projects = {self.state['project_id']: {}}
        make_server.return_value = server
        watcher = notifier_class.return_value.__enter__.return_value
        launcher.serve(self.config, self.folder / 'dashboard.json')
        watcher.watch.assert_called_once()
        kwargs = watcher.watch.call_args.kwargs
        self.assertTrue(kwargs['initialize_current'])
        self.assertEqual(kwargs['instance'], server.instance)
        self.assertTrue(kwargs['stop_event'].is_set())
        server.serve_forever.assert_called_once()
        server.server_close.assert_called_once()

    @patch('web_dashboard.make_server')
    def test_port_collision_uses_os_selected_loopback_port(self, make_server):
        server = Mock(server_port=54321, instance='fresh')
        server.dashboard.projects = {self.state['project_id']: {}}
        make_server.side_effect = [OSError('occupied'), server]
        launcher.serve(self.config, self.folder / 'dashboard.json')
        self.assertEqual(make_server.call_args_list[1].args, ([self.config], 0))
        self.assertEqual(launcher.read_state(self.folder / 'dashboard.json')['port'], 54321)
        server.server_close.assert_called_once()

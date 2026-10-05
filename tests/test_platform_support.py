"""Portable runtime checks; mocked Windows branches are not a native-host test."""
import errno
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import platform_support as platform
from state_io import atomic_write


class PlatformSupportTests(unittest.TestCase):
    def test_real_cross_process_lock_and_release(self):
        probe = ('import sys; sys.path.insert(0, sys.argv[1]); '
                 'from platform_support import acquire_lock; '
                 'f=open(sys.argv[2], "a"); acquire_lock(f, blocking=False)')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.lock'
            args = [sys.executable, '-c', probe, str(ROOT / 'scripts'), str(path)]
            with path.open('a') as handle:
                platform.acquire_lock(handle)
                result = subprocess.run(args, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('BlockingIOError', result.stderr)
            self.assertEqual(subprocess.run(args, capture_output=True, timeout=10).returncode, 0)

    def test_windows_lock_uses_first_byte(self):
        handle = Mock()
        handle.fileno.return_value = 12
        windows = SimpleNamespace(LK_NBLCK=2, locking=Mock())
        with patch.object(platform, 'IS_WINDOWS', True), patch.object(platform, 'msvcrt', windows, create=True):
            platform.acquire_lock(handle, blocking=False)
        handle.seek.assert_called_once_with(0)
        windows.locking.assert_called_once_with(12, 2, 1)

    def test_windows_nonblocking_contention_is_normalized(self):
        windows = SimpleNamespace(LK_NBLCK=2, locking=Mock(side_effect=OSError(errno.EACCES, 'locked')))
        with patch.object(platform, 'IS_WINDOWS', True), patch.object(platform, 'msvcrt', windows, create=True):
            with self.assertRaises(BlockingIOError):
                platform.acquire_lock(Mock(), blocking=False)

    def test_windows_blocking_lock_retries_contention(self):
        windows = SimpleNamespace(LK_NBLCK=2, locking=Mock(side_effect=[OSError(errno.EACCES, 'locked'), None]))
        with patch.object(platform, 'IS_WINDOWS', True), patch.object(platform, 'msvcrt', windows, create=True), patch.object(platform.time, 'sleep') as sleep:
            platform.acquire_lock(Mock())
        sleep.assert_called_once_with(0.05)
        self.assertEqual(windows.locking.call_count, 2)

    def test_windows_lock_propagates_real_io_errors(self):
        windows = SimpleNamespace(LK_NBLCK=2, locking=Mock(side_effect=OSError(errno.EBADF, 'bad fd')))
        with patch.object(platform, 'IS_WINDOWS', True), patch.object(platform, 'msvcrt', windows, create=True):
            with self.assertRaises(OSError) as caught:
                platform.acquire_lock(Mock())
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_detach_options_match_platform(self):
        with patch.object(platform, 'IS_WINDOWS', False):
            self.assertEqual(platform.detached_process_options(), {'start_new_session': True, 'close_fds': True})
        with patch.object(platform, 'IS_WINDOWS', True), patch.object(subprocess, 'DETACHED_PROCESS', 8, create=True), patch.object(subprocess, 'CREATE_NEW_PROCESS_GROUP', 512, create=True):
            self.assertEqual(platform.detached_process_options(), {'creationflags': 520, 'close_fds': True})

    def test_windows_pid_probe_never_calls_kill(self):
        with patch.object(platform, 'IS_WINDOWS', True), patch.object(platform, '_windows_process_alive', return_value=True) as probe, patch.object(platform.os, 'kill') as kill:
            self.assertTrue(platform.process_alive(123))
        probe.assert_called_once_with(123)
        kill.assert_not_called()

    def test_invalid_pid_never_signals(self):
        with patch.object(platform.os, 'kill') as kill:
            for pid in (None, 0, -1, True, '123'):
                self.assertFalse(platform.process_alive(pid))
        kill.assert_not_called()

    def test_windows_directory_sync_does_not_open_directory(self):
        with patch.object(platform, 'IS_WINDOWS', True), patch.object(platform.os, 'open') as opened:
            platform.sync_directory('unused')
        opened.assert_not_called()

    def test_atomic_utf8_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            atomic_write(path, '初次')
            atomic_write(path, '最终')
            self.assertEqual(path.read_text(encoding='utf-8'), '最终')
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_live_pid_probe(self):
        self.assertTrue(platform.process_alive(os.getpid()))

    @unittest.skipUnless(os.name == 'nt', 'requires actual Windows kernel')
    def test_native_windows_exited_process_probe(self):
        child = subprocess.Popen([sys.executable, '-c', 'pass'])
        child.wait(timeout=10)
        self.assertFalse(platform.process_alive(child.pid))


if __name__ == '__main__':
    unittest.main()

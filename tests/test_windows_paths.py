"""Windows path semantics exercised on a portable host."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import issue_worktree as w
import platform_support
from delegation_service import overlaps

class WindowsPathTests(unittest.TestCase):
    def test_reject_drive_unc_and_alternate_separators(self):
        for p in ['C:relative','C:/absolute','//server/share','src\\..\\secret','src/file:stream']:
            with self.subTest(p=p),self.assertRaises(ValueError):w.validate_paths([p])
    def test_windows_reserved_and_protected_aliases(self):
        with patch.object(w,'IS_WINDOWS',True):
            for p in ['.GIT/config','Reports/a','src/NUL.txt','src/COM1','src/name.','src/name ']:
                with self.subTest(p=p),self.assertRaises(ValueError):w.validate_paths([p])
    def test_scope_is_case_insensitive_on_windows(self):
        with patch.object(w,'IS_WINDOWS',True):
            self.assertTrue(w.within_scope('Src/a.py','src'))
            self.assertFalse(w.within_scope('src2/a.py','src'))
        with patch.object(platform_support,'IS_WINDOWS',True):
            self.assertTrue(overlaps('Src','src/a.py'))
    def test_posix_case_distinction_preserved(self):
        with patch.object(w,'IS_WINDOWS',False):
            self.assertFalse(w.within_scope('Src/a.py','src'))

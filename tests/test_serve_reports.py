"""Temporary localhost report-handler tests; no production services or records."""
from functools import partial
import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('serve_reports_test',ROOT/'scripts/serve_reports.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class QuietReports(module.Reports):
    def log_message(self,*args): pass

class ServeReportsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='report-server-test-')
        root=Path(self.tmp.name);self.reports=root/'reports';self.reports.mkdir()
        (self.reports/'report.html').write_bytes(b'<html>Fixture report</html>')
        self.outside=root/'outside.txt';self.outside.write_bytes(b'OUTSIDE-FIXTURE')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietReports,directory=str(self.reports)))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.tmp.cleanup()
    def test_report_bytes_and_head(self):
        from urllib.request import Request
        with urlopen(self.base+'/report.html',timeout=3) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(response.read(),b'<html>Fixture report</html>')
        with urlopen(Request(self.base+'/report.html',method='HEAD'),timeout=3) as response:
            self.assertEqual(response.status,200)
            self.assertEqual(response.read(),b'')
    def test_symlink_escape_refused(self):
        (self.reports/'outside.txt').symlink_to(self.outside)
        with self.assertRaises(HTTPError) as error:urlopen(self.base+'/outside.txt',timeout=3)
        self.assertEqual(error.exception.code,403)
    def test_parent_path_cannot_return_outside_bytes(self):
        for path in ['/../outside.txt','/%2e%2e/outside.txt']:
            with self.assertRaises(HTTPError) as error:urlopen(self.base+path,timeout=3)
            self.assertIn(error.exception.code,(403,404))

if __name__=='__main__':unittest.main()

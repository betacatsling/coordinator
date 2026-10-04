#!/usr/bin/env python3
"""Serve only the selected report directory on IPv4 loopback."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class Reports(SimpleHTTPRequestHandler):
    def send_head(self):
        root=Path(self.directory).resolve(strict=True)
        target=Path(self.translate_path(self.path)).resolve()
        if target!=root and root not in target.parents:
            self.send_error(403,'Outside report directory');return None
        return super().send_head()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--port',type=int,default=18765);a=p.parse_args()
    root=a.directory.resolve(strict=True)
    if not root.is_dir():raise ValueError('Report directory required')
    ThreadingHTTPServer(('127.0.0.1',a.port),partial(Reports,directory=str(root))).serve_forever()

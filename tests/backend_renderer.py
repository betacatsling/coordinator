"""Portable report fixture for HTTP byte checks; not the real HTML renderer."""
from html import escape
from pathlib import Path
import sys

draft = sys.stdin.read()
assert '--no-open' in sys.argv
Path(sys.argv[sys.argv.index('-o')+1]).write_text('<html><body><pre>'+escape(draft)+'</pre></body></html>')

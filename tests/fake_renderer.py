"""Renderer argument fixture; not the answer-me-with-html renderer."""
from pathlib import Path
import sys
source = sys.stdin.read()
Path(sys.argv[sys.argv.index('-o') + 1]).write_text('<html><body>Fixture report</body></html>')
assert '--no-open' in sys.argv
assert 'Fixture result' in source

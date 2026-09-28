"""Preview the website locally: python tools/serve.py  (then open http://localhost:8000)

Like `python -m http.server`, but tells the browser not to keep old copies of files,
so every edit shows up on a normal refresh.
"""

import functools
import http.server
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PORT = 8000


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    handler = functools.partial(NoCacheHandler, directory=str(SITE))
    print(f"Serving {SITE} at http://localhost:{PORT} (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("", PORT), handler).serve_forever()

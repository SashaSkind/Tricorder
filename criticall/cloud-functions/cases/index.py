"""
Study worklist -- EdgeOne Makers Python cloud function.

POST /cases  ->  { cases: [ {study_uid, accession, patient, indication, ...}, ... ] }

Feeds the incoming-studies worklist on the CritiCall dashboard.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from _cases import list_cases  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _write(self):
        payload = {"cases": list_cases()}
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._write()

    def do_GET(self):
        self._write()

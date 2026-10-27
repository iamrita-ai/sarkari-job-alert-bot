"""Minimal health-check HTTP server for Render / getvoroa.

Telegram bots are pull-based workers, but hosting platforms usually require
an HTTP port to report health. This tiny stdlib server answers ``/health``
without adding any web framework dependency.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path.split("?")[0] == "/health":
            body = json.dumps({"status": "ok", "service": "sarkari-job-alert-bot"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        logger.debug(fmt, *args)


def start_health_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="health-server", daemon=True)
    thread.start()
    logger.info("Health server listening on 0.0.0.0:%s/health", port)
    return server

"""Minimal health-check HTTP server for Render / getvoroa / Voroa.

Telegram bots are pull-based workers, but hosting platforms usually require
an HTTP port to report health. This tiny stdlib server answers ``/health``
without adding any web framework dependency, and exposes live scraper status.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

logger = logging.getLogger(__name__)


def start_health_server(
    port: int, status_provider: Callable[[], dict] | None = None
) -> ThreadingHTTPServer:
    class _HealthHandler(BaseHTTPRequestHandler):
        # Every hosting platform probes a path of its own: Render and Voroa
        # use "/", others use "/health" or "/healthz". Answer all of them
        # with HTTP 200 - a 404 on "/" is read as "the service is not up".
        HEALTH_PATHS = ("/", "/health", "/healthz", "/status", "/api/health")

        def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
            if self.path.split("?")[0] in self.HEALTH_PATHS:
                payload: dict = {"status": "ok", "service": "sarkari-job-alert-bot"}
                if status_provider is not None:
                    try:
                        payload["scraper"] = status_provider()
                    except Exception:  # noqa: BLE001 - health must never crash
                        logger.exception("Status provider failed")
                body = json.dumps(payload).encode()
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

    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="health-server", daemon=True)
    thread.start()
    logger.info("Health server listening on 0.0.0.0:%s/health", port)
    return server

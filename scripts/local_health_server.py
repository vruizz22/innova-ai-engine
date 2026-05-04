from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.pipeline.health import handler


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return

        response = handler({}, None)
        body = response.get("body", "{}")
        payload = body if isinstance(body, str) else json.dumps(body)

        self.send_response(int(response.get("statusCode", 200)))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload.encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 3010), HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()


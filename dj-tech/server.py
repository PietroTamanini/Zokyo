import os
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PANEL_API = os.environ.get("PANEL_API", "http://127.0.0.1:8000").rstrip("/")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5500"))


class Handler(SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        if self.path.startswith("/api/public/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.end_headers()
            return
        super().do_OPTIONS()

    def do_POST(self):
        if not self.path.startswith("/api/public/"):
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length)
        request = urllib.request.Request(
            PANEL_API + self.path,
            data=body,
            headers={
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Origin": self.headers.get("Origin", "http://127.0.0.1:5500"),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                self._copy_response(response.status, response.headers, response.read())
        except urllib.error.HTTPError as error:
            self._copy_response(error.code, error.headers, error.read())

    def _copy_response(self, status, headers, body):
        self.send_response(status)
        for key, value in headers.items():
            if key.lower() in {"connection", "content-length", "transfer-encoding"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

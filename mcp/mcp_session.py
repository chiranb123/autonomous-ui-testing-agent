import json
import subprocess
import threading
import queue
import time


class MCPSession:

    def __init__(self):
        self.process = None
        self.request_id = 1
        self._responses: "queue.Queue" = queue.Queue()
        self._reader_thread = None
        self._stop_reader = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self.process = subprocess.Popen(
            ["cmd", "/c", "npx", "@playwright/mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Single persistent background reader (no per-request thread overhead)
        self._stop_reader = False
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True
        )
        self._reader_thread.start()

        # Short readiness wait — initialize() will block until handshake completes
        time.sleep(0.3)

        if self.process.poll() is not None:
            raise RuntimeError("Playwright MCP failed to start")

        print("Playwright MCP server started")

    def stop(self):
        self._stop_reader = True
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            print("Playwright MCP server stopped")

    # ------------------------------------------------------------------
    # Background reader
    # ------------------------------------------------------------------

    def _reader_loop(self):
        """Continuously drain stdout into a queue."""
        try:
            while (
                not self._stop_reader
                and self.process
                and self.process.poll() is None
            ):
                line = self.process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    self._responses.put(json.loads(line))
                except json.JSONDecodeError:
                    # Ignore non-JSON server chatter
                    continue
        except Exception as exc:
            self._responses.put({"_error": str(exc)})

    # ------------------------------------------------------------------
    # IO
    # ------------------------------------------------------------------

    def send_message(self, message):
        payload = json.dumps(message)
        self.process.stdin.write(payload + "\n")
        self.process.stdin.flush()

    def read_response(self, timeout=30):
        try:
            return self._responses.get(timeout=timeout)
        except queue.Empty:
            return None

    def request(self, method, params=None):
        request_id = self.request_id
        self.request_id += 1

        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params:
            message["params"] = params

        self.send_message(message)

        # Match response by id — skip stray notifications
        deadline = time.time() + 30
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            response = self.read_response(timeout=remaining)
            if response is None:
                return None
            if "id" not in response or response.get("id") == request_id:
                return response
        return None

    def notify(self, method, params=None):
        message = {"jsonrpc": "2.0", "method": method}
        if params:
            message["params"] = params
        self.send_message(message)

    def initialize(self):
        response = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "autonomous-ui-testing-agent",
                    "version": "1.0.0",
                },
            },
        )
        self.notify("notifications/initialized")
        return response
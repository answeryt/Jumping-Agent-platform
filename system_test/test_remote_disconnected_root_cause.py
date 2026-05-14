"""
test_remote_disconnected_root_cause.py
----------------------------------------------------------------------
Diagnose the source of "Remote end closed connection without response".

This script does not require Docker and does not modify project files:
  STEP 1  Starts a local HTTP server that closes the socket without
          sending a response, proving urllib raises RemoteDisconnected.
  STEP 2  Simulates the same transient failure during AIO Sandbox startup
          and verifies SandboxManager._wait_until_ready retries until
          /v1/sandbox returns an HTTP response.

Run:
  python system_test/test_remote_disconnected_root_cause.py
----------------------------------------------------------------------
"""
from __future__ import annotations

import http.client
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, NoReturn, Optional
from urllib import request as urllib_request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sandbox_manager import SandboxInstance, SandboxManager  # type: ignore  # noqa: E402


_SEP = "=" * 70
_LINE = "-" * 70


def _banner(title: str) -> None:
    print(f"\n{_SEP}\n  {title}\n{_SEP}")


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _info(label: str, value: str) -> None:
    print(f"  -   {label:<28}{value}")


def _fail(reason: str, exc: Optional[BaseException] = None) -> NoReturn:
    print(f"\n{_LINE}\n  FAIL  Diagnostic failed\n")
    for line in reason.strip().splitlines():
        print(f"     {line}")
    if exc is not None:
        print(f"\n  [Exception type]  {type(exc).__name__}: {exc}")
        print("\n  [Traceback]")
        traceback.print_exc()
    print(f"{_LINE}\n")
    sys.exit(1)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _serve_one_disconnect(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", port))
        server.listen(1)
        conn, _addr = server.accept()
        with conn:
            # Read the request bytes, then close without sending an HTTP status line.
            conn.recv(4096)


def _step1_confirm_exception_type() -> None:
    _banner("STEP 1  Confirm disconnect exception type")
    port = _free_port()
    thread = threading.Thread(target=_serve_one_disconnect, args=(port,), daemon=True)
    thread.start()
    time.sleep(0.05)

    url = f"http://127.0.0.1:{port}/v1/sandbox"
    _info("Test URL", url)

    try:
        urllib_request.urlopen(url, timeout=2)
    except http.client.RemoteDisconnected as exc:
        _ok("Reproduced: urllib raises RemoteDisconnected when peer closes without response")
        _info("Exception text", str(exc))
        return
    except Exception as exc:
        _fail("Unexpected exception type; expected RemoteDisconnected", exc)

    _fail("The local disconnect server did not trigger an exception")


class _FlakyUrlopen:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        return _ReadyResponse()


class _ReadyResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def _step2_verify_sandbox_wait_handles_remote_disconnect() -> None:
    _banner("STEP 2  Verify SandboxManager retries transient disconnects")
    manager = SandboxManager(startup_timeout_seconds=3)
    instance = SandboxInstance(
        agent_name="diagnostic",
        container_name="diagnostic-sandbox",
        host_port=18080,
        base_url="http://localhost:18080",
        mcp_url="http://localhost:18080/mcp",
        dashboard_url="http://localhost:18080/index.html",
        vnc_url="http://localhost:18080/vnc/index.html?autoconnect=true",
    )

    fake_urlopen = _FlakyUrlopen()
    original_urlopen: Callable = urllib_request.urlopen
    urllib_request.urlopen = fake_urlopen  # type: ignore[assignment]
    try:
        manager._wait_until_ready(instance)
    except http.client.RemoteDisconnected as exc:
        _fail(
            "SandboxManager still does not catch RemoteDisconnected.\n"
            "This is the direct root cause of premature build failure.",
            exc,
        )
    except Exception as exc:
        _fail("Unexpected exception while waiting for sandbox readiness", exc)
    finally:
        urllib_request.urlopen = original_urlopen  # type: ignore[assignment]

    if fake_urlopen.calls < 2:
        _fail("No retry happened after the simulated first disconnect")

    _ok("SandboxManager treats RemoteDisconnected as not-ready and retries")
    _info("urlopen calls", str(fake_urlopen.calls))


def main() -> None:
    _step1_confirm_exception_type()
    _step2_verify_sandbox_wait_handles_remote_disconnect()
    _banner("Conclusion")
    _ok("Root cause: AIO Sandbox may briefly close HTTP connections during startup; readiness waits must catch and retry it.")


if __name__ == "__main__":
    main()

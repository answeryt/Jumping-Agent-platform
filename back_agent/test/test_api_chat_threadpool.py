import asyncio
import threading

import httpx

import back_agent.api as api


class RecordingFlow:
    def __init__(self, event_loop_thread_id: int) -> None:
        self.event_loop_thread_id = event_loop_thread_id
        self.run_thread_id: int | None = None
        self.run_had_running_loop: bool | None = None
        self.received_input: str | None = None

    def run(self, user_input: str) -> str:
        self.received_input = user_input
        self.run_thread_id = threading.get_ident()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.run_had_running_loop = False
        else:
            self.run_had_running_loop = True
        return "threadpool answer"


async def _post_chat(flow: RecordingFlow) -> httpx.Response:
    transport = httpx.ASGITransport(app=api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/chat", json={"user_input": "hello"})


def test_chat_runs_sync_flow_in_threadpool(monkeypatch) -> None:
    event_loop_thread_id: int | None = None

    async def exercise() -> httpx.Response:
        nonlocal event_loop_thread_id
        event_loop_thread_id = threading.get_ident()
        flow = RecordingFlow(event_loop_thread_id=event_loop_thread_id)
        monkeypatch.setattr(api, "_get_flow", lambda: flow)

        response = await _post_chat(flow)

        assert flow.received_input == "hello"
        assert flow.run_thread_id != event_loop_thread_id
        assert flow.run_had_running_loop is False
        return response

    response = asyncio.run(exercise())

    assert response.status_code == 200
    assert response.json() == {"answer": "threadpool answer"}

from __future__ import annotations

from fastapi.testclient import TestClient

import backend.orchestrator as orchestrator


def test_chat_without_workspace_returns_readable_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(orchestrator, "WORKSPACE_ROOT", tmp_path)

    client = TestClient(orchestrator.app)
    response = client.post("/chat", json={"user_input": "hello"})

    assert response.status_code == 404
    assert response.json() == {
        "detail": "No runnable agent workspace found in backend/workspace"
    }

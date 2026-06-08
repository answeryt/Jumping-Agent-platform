from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Optional


GatewayCaller = Callable[[str, Dict[str, Any], Optional[int]], Any]
WaitForRun = Callable[[str, str, int], Dict[str, Any]]
RetireRuntime = Callable[[str, str], Any]


def annotate_inter_session_message(
    message: str,
    *,
    source_session_key: Optional[str] = None,
    source_channel: Optional[str] = None,
    source_tool: str = "sessions_send",
) -> str:
    meta = {
        "kind": "inter_session",
        "sourceSessionKey": source_session_key,
        "sourceChannel": source_channel,
        "sourceTool": source_tool,
        "isUser": False,
    }
    return f"[Inter-session message: {meta}]\n{message}"


def run_agent_step(
    *,
    session_key: str,
    message: str,
    extra_system_prompt: str,
    timeout_ms: int,
    gateway: GatewayCaller,
    wait_for_run: Optional[WaitForRun] = None,
    retire_runtime: Optional[RetireRuntime] = None,
    channel: str = "internal",
    lane: Optional[str] = None,
    transcript_message: Optional[str] = None,
    agent_command_from_ingress: Optional[Callable[[Dict[str, Any]], Any]] = None,
    source_session_key: Optional[str] = None,
    source_channel: Optional[str] = None,
    source_tool: str = "sessions_send",
) -> Optional[str]:
    """Python migration of TS `runAgentStep`.

    It starts a nested agent turn, waits for the assistant reply when a wait hook is
    supplied, and retires the session MCP runtime only after a terminal result.
    """

    step_id = uuid.uuid4().hex
    prompt = annotate_inter_session_message(
        message,
        source_session_key=source_session_key,
        source_channel=source_channel,
        source_tool=source_tool,
    )
    resolved_lane = lane or f"nested:{session_key}"
    input_provenance = {
        "kind": "inter_session",
        "sourceSessionKey": source_session_key,
        "sourceChannel": source_channel,
        "sourceTool": source_tool,
    }

    if transcript_message is not None:
        if agent_command_from_ingress is None:
            raise RuntimeError("agent_command_from_ingress required when transcript_message is provided")
        result = agent_command_from_ingress(
            {
                "message": prompt,
                "transcriptMessage": transcript_message,
                "sessionKey": session_key,
                "deliver": False,
                "channel": channel,
                "lane": resolved_lane,
                "runId": step_id,
                "extraSystemPrompt": extra_system_prompt,
                "inputProvenance": input_provenance,
                "allowModelOverride": False,
            }
        )
        if retire_runtime:
            retire_runtime(session_key, "nested-agent-step-complete")
        return _extract_reply(result)

    response = gateway(
        "agent",
        {
            "message": prompt,
            "sessionKey": session_key,
            "idempotencyKey": step_id,
            "deliver": False,
            "channel": channel,
            "lane": resolved_lane,
            "extraSystemPrompt": extra_system_prompt,
            "inputProvenance": input_provenance,
        },
        10000,
    )
    run_id = response.get("runId") if isinstance(response, dict) else None
    resolved_run_id = str(run_id or step_id)
    if wait_for_run is None:
        return None
    result = wait_for_run(resolved_run_id, session_key, min(int(timeout_ms), 60000))
    status = result.get("status")
    if status in {"ok", "error"} and retire_runtime:
        retire_runtime(session_key, "nested-agent-step-complete")
    if status != "ok":
        return None
    reply = result.get("replyText")
    return str(reply) if reply is not None else None


def _extract_reply(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    payloads = result.get("payloads")
    if not isinstance(payloads, list):
        return None
    texts = [
        str(item.get("text")).strip()
        for item in payloads
        if isinstance(item, dict) and isinstance(item.get("text"), str) and item.get("text", "").strip()
    ]
    return "\n\n".join(texts) if texts else None


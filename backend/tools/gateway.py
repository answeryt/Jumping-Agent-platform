from __future__ import annotations

from typing import Any, Callable, Dict, Optional


GatewayCaller = Callable[[str, Dict[str, Any], Optional[int]], Any]


DEFAULT_GATEWAY_URL = "ws://127.0.0.1:18789"


def read_gateway_call_options(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "gatewayUrl": params.get("gatewayUrl"),
        "gatewayToken": params.get("gatewayToken"),
        "timeoutMs": params.get("timeoutMs"),
    }


def call_gateway_tool(
    gateway: GatewayCaller,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    timeout_ms: Optional[int] = None,
) -> Any:
    return gateway(method, params or {}, timeout_ms)


__all__ = ["DEFAULT_GATEWAY_URL", "GatewayCaller", "call_gateway_tool", "read_gateway_call_options"]


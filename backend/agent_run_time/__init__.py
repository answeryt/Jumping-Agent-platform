from __future__ import annotations

__all__ = [
    "AgentRuntimeRegistry",
    "AgentToolRuntime",
    "LSMFallbackLayer",
    "LSMRepairRequest",
    "RuntimeToolStep",
    "ToolExecutionObservation",
]


def __getattr__(name: str):
    if name in {"AgentRuntimeRegistry"}:
        from .agent_runtime import AgentRuntimeRegistry

        return {"AgentRuntimeRegistry": AgentRuntimeRegistry}[name]
    if name in {"LSMFallbackLayer", "LSMRepairRequest"}:
        from .lsm_layer import LSMFallbackLayer, LSMRepairRequest

        return {"LSMFallbackLayer": LSMFallbackLayer, "LSMRepairRequest": LSMRepairRequest}[name]
    if name in {"AgentToolRuntime", "RuntimeToolStep", "ToolExecutionObservation"}:
        from .tool_runtime import AgentToolRuntime, RuntimeToolStep, ToolExecutionObservation

        return {
            "AgentToolRuntime": AgentToolRuntime,
            "RuntimeToolStep": RuntimeToolStep,
            "ToolExecutionObservation": ToolExecutionObservation,
        }[name]
    raise AttributeError(name)

from __future__ import annotations

from typing import Any

from workflow.baseflow import BaseFlow
from workflow.react_agent_workflow import ReactAgentWorkflow


class FlowFactory:
    """Flow 工厂：根据类型创建具体 flow 实现。"""

    _FLOW_REGISTRY = {
        "react": ReactAgentWorkflow,
    }

    @classmethod
    def create(cls, flow_type: str, **kwargs: Any) -> BaseFlow:
        flow_key = flow_type.strip().lower()
        flow_cls = cls._FLOW_REGISTRY.get(flow_key)
        if flow_cls is None:
            supported = ", ".join(sorted(cls._FLOW_REGISTRY))
            raise ValueError(f"不支持的 flow_type: {flow_type}，可选: {supported}")
        return flow_cls(**kwargs)

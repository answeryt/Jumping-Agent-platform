from __future__ import annotations

from typing import Any

try:
    from .baseflow import BaseFlow
    from .react_agent_workflow import ReactAgentWorkflow
except ImportError:  # pragma: no cover - legacy top-level imports
    from workflow.baseflow import BaseFlow
    from workflow.react_agent_workflow import ReactAgentWorkflow


class FlowFactory:
    """Flow 工厂：根据类型创建具体 flow 实现。"""

    # 当前 back_agent 只有 react 这一种 flow；以后要扩展就在这里注册。
    _FLOW_REGISTRY = {
        "react": ReactAgentWorkflow,
    }

    @classmethod
    def create(cls, flow_type: str, **kwargs: Any) -> BaseFlow:
        # 工厂只负责选择实现类，不参与 prompt、model、tool 的具体配置。
        flow_key = flow_type.strip().lower()
        flow_cls = cls._FLOW_REGISTRY.get(flow_key)
        if flow_cls is None:
            supported = ", ".join(sorted(cls._FLOW_REGISTRY))
            raise ValueError(f"不支持的 flow_type: {flow_type}，可选: {supported}")
        return flow_cls(**kwargs)

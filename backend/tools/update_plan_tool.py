from __future__ import annotations

from typing import Any, Dict

from .core import BackendTool, ToolInputError, ToolResult, read_string
from .runtime_shared import schema


PLAN_STEP_STATUSES = {"pending", "in_progress", "completed"}


def create_update_plan_tool() -> BackendTool:
    """Update ordered task plan; max one in_progress step."""

    def execute(params: Dict[str, Any]) -> ToolResult:
        raw_plan = params.get("plan")
        if not isinstance(raw_plan, list) or not raw_plan:
            raise ToolInputError("plan required")
        plan = []
        for index, item in enumerate(raw_plan):
            if not isinstance(item, dict):
                raise ToolInputError(f"plan[{index}] must be an object")
            step = read_string(item, "step", required=True)
            status = read_string(item, "status", required=True)
            if status not in PLAN_STEP_STATUSES:
                raise ToolInputError(
                    f"plan[{index}].status must be one of {', '.join(sorted(PLAN_STEP_STATUSES))}"
                )
            plan.append({"step": step, "status": status})
        if sum(1 for item in plan if item["status"] == "in_progress") > 1:
            raise ToolInputError("plan can contain at most one in_progress step")
        details = {"status": "updated", "plan": plan}
        explanation = read_string(params, "explanation")
        if explanation:
            details["explanation"] = explanation
        return ToolResult(content=[], details=details)

    return BackendTool(
        name="update_plan",
        label="Update Plan",
        display_summary="Update task plan.",
        description="Update ordered task plan; max one in_progress step.",
        parameters=schema(
            {"explanation": {"type": "string"}, "plan": {"type": "array", "items": {"type": "object"}}},
            ["plan"],
        ),
        execute=execute,
    )


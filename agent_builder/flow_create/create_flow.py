"""
create_flow.py

用法：
    python agent_builder/flow_create/create_flow.py sequential --agents "researcher,writer,reviewer"
    python agent_builder/flow_create/create_flow.py router --dispatcher "classifier" --branches "tech:tech_agent,finance:finance_agent"
    python agent_builder/flow_create/create_flow.py parallel --dispatcher "splitter" --workers "a,b,c" --aggregator "merger"
    python agent_builder/flow_create/create_flow.py loop --executor "coder" --evaluator "reviewer" --max-iterations 5
    python agent_builder/flow_create/create_flow.py debate --participants "optimist,pessimist,realist" --moderator "judge"
    python agent_builder/flow_create/create_flow.py hierarchical --manager "pm" --workers "dev,tester,designer"
    python agent_builder/flow_create/create_flow.py supervisor --supervisor "lead" --agents "planner,researcher,builder,reviewer"

会自动生成（写入沙盒容器 /workspace/）：
    Workflow/<flow_type>_flow.py
    以及每个涉及的 agent 骨架（复用 create_agent.py）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 导入 flow 模板
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flow_template import (
    sequential_flow_py,
    router_flow_py,
    parallel_flow_py,
    loop_flow_py,
    debate_flow_py,
    hierarchical_flow_py,
    supervisor_flow_py,
)
from agent_create.create_agent import create_agent

# 导入沙盒执行器
SANDBOX_ROOT = PROJECT_ROOT / "sandbox"
sys.path.insert(0, str(SANDBOX_ROOT))
from sandbox_executor import SandboxExecutor  # type: ignore


# ─────────────────────────────────────────────
# 辅助函数
# ───────────────────��─────────────────────────

def _split_names(raw: str) -> List[str]:
    """将逗号分隔的名称字符串拆分为列表。"""
    return [n.strip().lower().replace("-", "_") for n in raw.split(",") if n.strip()]


def _parse_branches(raw: str) -> Dict[str, str]:
    """
    解析 branches 参数。
    格式: "key1:agent1,key2:agent2"
    """
    branches: Dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" not in pair:
            print(f"警告：跳过无效 branch 格式: {pair}", file=sys.stderr)
            continue
        key, agent = pair.split(":", 1)
        branches[key.strip().lower()] = agent.strip().lower().replace("-", "_")
    return branches


def _write_flow_file(
    executor: SandboxExecutor,
    flow_type: str,
    content: str,
) -> None:
    """将 Flow 文件写入沙盒容器。"""
    container_path = f"/workspace/Workflow/{flow_type}_flow.py"
    check = executor.run(["test", "-f", container_path])
    if check.returncode == 0:
        print(f"已存在，跳过：{container_path}")
        return
    result = executor.write_file(container_path, content)
    if result.ok:
        print(f"已生成：{container_path}")
    else:
        print(f"写入失败：{container_path}\n{result.stderr}", file=sys.stderr)


def _ensure_agents(agent_names: List[str], executor: SandboxExecutor) -> None:
    """为所有涉及的 agent 生成骨架（复用 create_agent.py）。"""
    for name in agent_names:
        create_agent(name, executor=executor)


# ─────────────────────────────────────────────
# 各 Flow 类���的创建入口
# ─────────────────────────────────────────────

def create_sequential(args: argparse.Namespace, executor: SandboxExecutor) -> None:
    agents = _split_names(args.agents)
    if len(agents) < 2:
        print("错误：sequential flow 至少需要 2 个 agent", file=sys.stderr)
        sys.exit(1)
    _ensure_agents(agents, executor)
    content = sequential_flow_py(agents)
    _write_flow_file(executor, "sequential", content)
    print(f"\nSequentialFlow 已生成，agent 顺序: {' → '.join(agents)}")


def create_router(args: argparse.Namespace, executor: SandboxExecutor) -> None:
    dispatcher = args.dispatcher.strip().lower().replace("-", "_")
    branches = _parse_branches(args.branches)
    if not branches:
        print("错误：router flow 至少需要 1 个 branch", file=sys.stderr)
        sys.exit(1)
    all_agents = [dispatcher] + list(branches.values())
    _ensure_agents(all_agents, executor)
    content = router_flow_py(dispatcher, branches)
    _write_flow_file(executor, "router", content)
    branch_desc = ", ".join(f"{k} → {v}" for k, v in branches.items())
    print(f"\nRouterFlow 已生成，dispatcher: {dispatcher}, branches: {branch_desc}")


def create_parallel(args: argparse.Namespace, executor: SandboxExecutor) -> None:
    dispatcher = args.dispatcher.strip().lower().replace("-", "_")
    workers = _split_names(args.workers)
    aggregator = args.aggregator.strip().lower().replace("-", "_")
    if len(workers) < 2:
        print("错误：parallel flow 至少需要 2 个 worker", file=sys.stderr)
        sys.exit(1)
    all_agents = [dispatcher] + workers + [aggregator]
    _ensure_agents(all_agents, executor)
    content = parallel_flow_py(dispatcher, workers, aggregator)
    _write_flow_file(executor, "parallel", content)
    print(f"\nParallelFlow 已生成，dispatcher: {dispatcher}, workers: {workers}, aggregator: {aggregator}")


def create_loop(args: argparse.Namespace, executor: SandboxExecutor) -> None:
    executor_name = args.executor.strip().lower().replace("-", "_")
    evaluator = args.evaluator.strip().lower().replace("-", "_")
    max_iter = int(args.max_iterations)
    _ensure_agents([executor_name, evaluator], executor)
    content = loop_flow_py(executor_name, evaluator, max_iter)
    _write_flow_file(executor, "loop", content)
    print(f"\nLoopFlow 已生成，executor: {executor_name}, evaluator: {evaluator}, max_iterations: {max_iter}")


def create_debate(args: argparse.Namespace, executor: SandboxExecutor) -> None:
    participants = _split_names(args.participants)
    moderator = args.moderator.strip().lower().replace("-", "_")
    max_rounds = int(args.max_rounds)
    if len(participants) < 2:
        print("错误：debate flow 至少需要 2 个 participant", file=sys.stderr)
        sys.exit(1)
    all_agents = participants + [moderator]
    _ensure_agents(all_agents, executor)
    content = debate_flow_py(participants, moderator, max_rounds)
    _write_flow_file(executor, "debate", content)
    print(f"\nDebateFlow 已生成，participants: {participants}, moderator: {moderator}, max_rounds: {max_rounds}")


def create_hierarchical(args: argparse.Namespace, executor: SandboxExecutor) -> None:
    manager = args.manager.strip().lower().replace("-", "_")
    workers = _split_names(args.workers)
    max_rounds = int(args.max_delegation_rounds)
    if not workers:
        print("错误：hierarchical flow 至少需要 1 个 worker", file=sys.stderr)
        sys.exit(1)
    all_agents = [manager] + workers
    _ensure_agents(all_agents, executor)
    content = hierarchical_flow_py(manager, workers, max_rounds)
    _write_flow_file(executor, "hierarchical", content)
    print(f"\nHierarchicalFlow 已生成，manager: {manager}, workers: {workers}")


def create_supervisor(args: argparse.Namespace, executor: SandboxExecutor) -> None:
    supervisor = args.supervisor.strip().lower().replace("-", "_")
    agents = _split_names(args.agents)
    max_rounds = int(args.max_rounds)
    if not agents:
        print("错误：supervisor flow 至少需要 1 个可调度 agent", file=sys.stderr)
        sys.exit(1)
    all_agents = [supervisor] + agents
    _ensure_agents(all_agents, executor)
    content = supervisor_flow_py(supervisor, agents, max_rounds)
    _write_flow_file(executor, "supervisor", content)
    print(f"\nSupervisorFlow 已生成，supervisor: {supervisor}, agents: {agents}, max_rounds: {max_rounds}")


# ─────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="自动生成 Flow 骨架及关联 Agent（写入沙盒容器）"
    )
    subparsers = parser.add_subparsers(dest="flow_type", help="Flow 类型")
    subparsers.required = True

    # sequential
    sp_seq = subparsers.add_parser("sequential", help="顺序链 Flow")
    sp_seq.add_argument("--agents", required=True, help="逗号分隔的 agent 名称，按执行顺序排列")

    # router
    sp_router = subparsers.add_parser("router", help="条件路由 Flow")
    sp_router.add_argument("--dispatcher", required=True, help="路由分发 agent 名称")
    sp_router.add_argument("--branches", required=True, help="条件映射，格式: key1:agent1,key2:agent2")

    # parallel
    sp_par = subparsers.add_parser("parallel", help="并行扇出-汇总 Flow")
    sp_par.add_argument("--dispatcher", required=True, help="任务拆分 agent 名称")
    sp_par.add_argument("--workers", required=True, help="逗号分隔的 worker agent 名称")
    sp_par.add_argument("--aggregator", required=True, help="结果汇总 agent 名称")

    # loop
    sp_loop = subparsers.add_parser("loop", help="循环反思 Flow")
    sp_loop.add_argument("--executor", required=True, help="执行 agent 名称")
    sp_loop.add_argument("--evaluator", required=True, help="评估 agent 名称")
    sp_loop.add_argument("--max-iterations", default=5, type=int, help="最大迭代次数（默认 5）")

    # debate
    sp_debate = subparsers.add_parser("debate", help="多方讨论 Flow")
    sp_debate.add_argument("--participants", required=True, help="逗号分隔的参与者 agent 名称")
    sp_debate.add_argument("--moderator", required=True, help="主持人 agent 名称")
    sp_debate.add_argument("--max-rounds", default=5, type=int, help="最大讨论轮次（默认 5）")

    # hierarchical
    sp_hier = subparsers.add_parser("hierarchical", help="层级委派 Flow")
    sp_hier.add_argument("--manager", required=True, help="管理者 agent 名称")
    sp_hier.add_argument("--workers", required=True, help="逗号分隔的 worker agent 名称")
    sp_hier.add_argument("--max-delegation-rounds", default=3, type=int, help="最大委派轮次（默认 3）")

    # supervisor
    sp_supervisor = subparsers.add_parser("supervisor", help="监督编排 Flow")
    sp_supervisor.add_argument("--supervisor", required=True, help="监督/编排 agent 名称")
    sp_supervisor.add_argument("--agents", required=True, help="逗号分隔的可调度 agent 名称")
    sp_supervisor.add_argument("--max-rounds", default=5, type=int, help="最大调度轮次（默认 5）")

    args = parser.parse_args()
    executor = SandboxExecutor()

    dispatch = {
        "sequential": create_sequential,
        "router": create_router,
        "parallel": create_parallel,
        "loop": create_loop,
        "debate": create_debate,
        "hierarchical": create_hierarchical,
        "supervisor": create_supervisor,
    }

    handler = dispatch.get(args.flow_type)
    if handler is None:
        print(f"错误：未知的 flow_type: {args.flow_type}", file=sys.stderr)
        sys.exit(1)
    handler(args, executor)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_create.create_agent import create_agent
from common.local_executor import ExecutorProtocol, LocalWorkspaceExecutor
from common.naming import normalize_python_name
from flow_template.flow_templete import (
    debate_flow_py,
    hierarchical_flow_py,
    loop_flow_py,
    parallel_flow_py,
    router_flow_py,
    sequential_flow_py,
)


def _split_names(raw: str) -> List[str]:
    return [normalize_python_name(name, "agent") for name in raw.split(",") if name.strip()]


def _parse_branches(raw: str) -> Dict[str, str]:
    branches: Dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" not in pair:
            continue
        key, agent = pair.split(":", 1)
        branches[key.strip().lower()] = normalize_python_name(agent, "agent")
    return branches


def _write_flow_file(executor: ExecutorProtocol, flow_type: str, content: str) -> None:
    container_path = f"/workspace/Workflow/{flow_type}_flow.py"
    if executor.run(["test", "-f", container_path]).returncode == 0:
        return
    result = executor.write_file(container_path, content)
    if not result.ok:
        print(f"failed to write: {container_path}\n{result.stderr}", file=sys.stderr)


def _ensure_agents(agent_names: List[str], executor: ExecutorProtocol) -> None:
    for name in agent_names:
        create_agent(name, executor=executor)


def create_sequential(args: argparse.Namespace, executor: ExecutorProtocol) -> None:
    agents = _split_names(args.agents)
    if len(agents) < 2:
        print("sequential flow requires at least 2 agents", file=sys.stderr)
        sys.exit(1)
    _ensure_agents(agents, executor)
    _write_flow_file(executor, "sequential", sequential_flow_py(agents))


def create_router(args: argparse.Namespace, executor: ExecutorProtocol) -> None:
    dispatcher = normalize_python_name(args.dispatcher, "agent")
    branches = _parse_branches(args.branches)
    if not branches:
        print("router flow requires at least 1 branch", file=sys.stderr)
        sys.exit(1)
    _ensure_agents([dispatcher, *branches.values()], executor)
    _write_flow_file(executor, "router", router_flow_py(dispatcher, branches))


def create_parallel(args: argparse.Namespace, executor: ExecutorProtocol) -> None:
    dispatcher = normalize_python_name(args.dispatcher, "agent")
    workers = _split_names(args.workers)
    aggregator = normalize_python_name(args.aggregator, "agent")
    if len(workers) < 2:
        print("parallel flow requires at least 2 workers", file=sys.stderr)
        sys.exit(1)
    _ensure_agents([dispatcher, *workers, aggregator], executor)
    _write_flow_file(executor, "parallel", parallel_flow_py(dispatcher, workers, aggregator))


def create_loop(args: argparse.Namespace, executor: ExecutorProtocol) -> None:
    executor_name = normalize_python_name(args.executor, "agent")
    evaluator = normalize_python_name(args.evaluator, "agent")
    _ensure_agents([executor_name, evaluator], executor)
    _write_flow_file(executor, "loop", loop_flow_py(executor_name, evaluator, int(args.max_iterations)))


def create_debate(args: argparse.Namespace, executor: ExecutorProtocol) -> None:
    participants = _split_names(args.participants)
    moderator = normalize_python_name(args.moderator, "agent")
    if len(participants) < 2:
        print("debate flow requires at least 2 participants", file=sys.stderr)
        sys.exit(1)
    _ensure_agents([*participants, moderator], executor)
    _write_flow_file(executor, "debate", debate_flow_py(participants, moderator, int(args.max_rounds)))


def create_hierarchical(args: argparse.Namespace, executor: ExecutorProtocol) -> None:
    manager = normalize_python_name(args.manager, "agent")
    workers = _split_names(args.workers)
    if not workers:
        print("hierarchical flow requires at least 1 worker", file=sys.stderr)
        sys.exit(1)
    _ensure_agents([manager, *workers], executor)
    _write_flow_file(
        executor,
        "hierarchical",
        hierarchical_flow_py(manager, workers, int(args.max_delegation_rounds)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create generated flow files and related agents.")
    subparsers = parser.add_subparsers(dest="flow_type", required=True)

    sp_seq = subparsers.add_parser("sequential")
    sp_seq.add_argument("--agents", required=True)

    sp_router = subparsers.add_parser("router")
    sp_router.add_argument("--dispatcher", required=True)
    sp_router.add_argument("--branches", required=True)

    sp_par = subparsers.add_parser("parallel")
    sp_par.add_argument("--dispatcher", required=True)
    sp_par.add_argument("--workers", required=True)
    sp_par.add_argument("--aggregator", required=True)

    sp_loop = subparsers.add_parser("loop")
    sp_loop.add_argument("--executor", required=True)
    sp_loop.add_argument("--evaluator", required=True)
    sp_loop.add_argument("--max-iterations", dest="max_iterations", default=5, type=int)

    sp_debate = subparsers.add_parser("debate")
    sp_debate.add_argument("--participants", required=True)
    sp_debate.add_argument("--moderator", required=True)
    sp_debate.add_argument("--max-rounds", dest="max_rounds", default=5, type=int)

    sp_hier = subparsers.add_parser("hierarchical")
    sp_hier.add_argument("--manager", required=True)
    sp_hier.add_argument("--workers", required=True)
    sp_hier.add_argument("--max-delegation-rounds", dest="max_delegation_rounds", default=3, type=int)

    args = parser.parse_args()
    executor = LocalWorkspaceExecutor(PROJECT_ROOT / "workspace")
    dispatch = {
        "sequential": create_sequential,
        "router": create_router,
        "parallel": create_parallel,
        "loop": create_loop,
        "debate": create_debate,
        "hierarchical": create_hierarchical,
    }
    dispatch[args.flow_type](args, executor)


if __name__ == "__main__":
    main()

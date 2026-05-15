"""
test_router_memory_compaction_connection.py
----------------------------------------------------------------------
Verify that router_memory_compaction_test is connected to backend.memory.

This script calls the generated workflow entrypoint directly:
  backend/workspace/router_memory_compaction_test/Workflow/run_router_flow.py

It checks:
  1. RouterFlow writes Agent messages into backend.memory.AgentWorkingMemory.
  2. Short-term memory crosses the auto-compact threshold.
  3. Context compaction trims persisted rows and injects a summary.
  4. AgentLongTermMemory record/retrieve tool methods work on the same store.

Run:
  python system_test/test_router_memory_compaction_connection.py
----------------------------------------------------------------------
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, NoReturn


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
WORKSPACE_ROOT = BACKEND_ROOT / "workspace" / "router_memory_compaction_test"
RUN_ROUTER_FLOW = WORKSPACE_ROOT / "Workflow" / "run_router_flow.py"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from backend.memory._long_term_memory import AgentLongTermMemory  # noqa: E402
from backend.memory.working_memory import AgentWorkingMemory, Msg  # noqa: E402


_SEP = "=" * 78
_LINE = "-" * 78


def _banner(title: str) -> None:
    print(f"\n{_SEP}\n  {title}\n{_SEP}")


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _info(label: str, value: Any) -> None:
    print(f"  -   {label:<32}{value}")


def _fail(reason: str, exc: BaseException | None = None) -> NoReturn:
    print(f"\n{_LINE}\n  FAIL  Router memory compaction test failed\n")
    for line in reason.strip().splitlines():
        print(f"     {line}")
    if exc is not None:
        print(f"\n  [Exception type]  {type(exc).__name__}: {exc}")
        print("\n  [Traceback]")
        traceback.print_exc()
    print(f"{_LINE}\n")
    sys.exit(1)


def _db_arg(memory_db: Path) -> str:
    try:
        return str(memory_db.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(memory_db)


def _test_env(memory_db: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(PROJECT_ROOT),
            str(WORKSPACE_ROOT),
            env.get("PYTHONPATH", ""),
        ],
    )
    env["AGENT_WORKING_MEMORY_DB"] = _db_arg(memory_db)
    env["AGENT_LONG_TERM_MEMORY_DB"] = _db_arg(memory_db)
    # Keep the test deterministic: threshold = (34000 - 1000) - 13000 = 20000 tokens.
    env["AGENT_AUTO_COMPACT_WINDOW"] = "34000"
    env["AGENT_MAX_OUTPUT_TOKENS"] = "1000"
    env.pop("DISABLE_COMPACT", None)
    env.pop("DISABLE_AUTO_COMPACT", None)
    env.pop("AGENT_DISABLE_AUTO_COMPACT", None)
    return env


def _connect(memory_db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(memory_db)
    conn.row_factory = sqlite3.Row
    return conn


def _run_router_once(
    *,
    memory_db: Path,
    user_id: str,
    session_id: str,
    question: str,
) -> str:
    cmd = [
        sys.executable,
        str(RUN_ROUTER_FLOW),
        "--user-id",
        user_id,
        "--session-id",
        session_id,
        "--memory-db",
        _db_arg(memory_db),
        "--once",
        question,
        "--verbose",
    ]
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        env=_test_env(memory_db),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        _fail(
            "run_router_flow.py returned a non-zero exit code.\n"
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}",
        )
    if "math_agent" not in result.stdout or "route_complete" not in result.stdout:
        _fail(
            "The router flow did not complete through the deterministic math branch.\n"
            f"STDOUT:\n{result.stdout}",
        )
    return result.stdout


def _count_rows(memory_db: Path, user_id: str, session_id: str) -> int:
    with _connect(memory_db) as conn:
        return int(
            conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM working_memory
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()["count"],
        )


def _agent_keys(memory_db: Path, user_id: str, session_id: str) -> set[str]:
    with _connect(memory_db) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT agent_key
            FROM working_memory
            WHERE user_id = ? AND session_id = ?
            """,
            (user_id, session_id),
        ).fetchall()
    return {row["agent_key"] for row in rows}


def _compaction_state(memory_db: Path, user_id: str, session_id: str) -> sqlite3.Row | None:
    with _connect(memory_db) as conn:
        return conn.execute(
            """
            SELECT summary, last_summarized_id, consecutive_failures, turn_counter
            FROM working_memory_compaction_state
            WHERE user_id = ? AND session_id = ?
            """,
            (user_id, session_id),
        ).fetchone()


def _oversized_math_question(index: int, marker: str) -> str:
    payload = (
        f"{marker}-turn-{index} "
        "请计算 12345 + 67890，并记住这段上下文用于压缩测试。"
        "alpha beta gamma delta epsilon zeta eta theta "
    )
    return (payload * 210) + f" 这是第 {index} 轮，最后仍然请计算 12345 + 67890。"


def _step1_verify_working_memory_connection(memory_db: Path, user_id: str, session_id: str) -> None:
    _banner("STEP 1  Verify RouterFlow writes to AgentWorkingMemory")
    output = _run_router_once(
        memory_db=memory_db,
        user_id=user_id,
        session_id=session_id,
        question="请计算 12 + 30，并把结果返回。",
    )
    keys = _agent_keys(memory_db, user_id, session_id)
    row_count = _count_rows(memory_db, user_id, session_id)
    expected_keys = {"shared", "dispatcher", "math_agent"}
    if not expected_keys.issubset(keys):
        _fail(f"Missing expected agent memory keys. expected={expected_keys}, actual={keys}")
    if row_count < 3:
        _fail(f"Expected at least 3 working_memory rows, got {row_count}")
    _ok("run_router_flow.py persisted shared, dispatcher, and math_agent messages")
    _info("working_memory rows", row_count)
    _info("agent keys", ", ".join(sorted(keys)))
    _info("sample output", " ".join(output.splitlines()[-4:])[:180])


def _step2_trigger_short_term_compaction(memory_db: Path, user_id: str, session_id: str) -> None:
    _banner("STEP 2  Trigger short-term threshold and context compaction")
    marker = f"router-memory-marker-{uuid.uuid4().hex[:10]}"
    raw_turns = 1
    for index in range(1, 4):
        _run_router_once(
            memory_db=memory_db,
            user_id=user_id,
            session_id=session_id,
            question=_oversized_math_question(index, marker),
        )
        raw_turns += 1

    memory = AgentWorkingMemory(memory_db, user_id=user_id, session_id=session_id)
    warning_state = memory.token_warning_state()
    state = _compaction_state(memory_db, user_id, session_id)
    persisted_rows = _count_rows(memory_db, user_id, session_id)
    expected_uncompacted_rows = raw_turns * 3

    if state is None:
        _fail("No working_memory_compaction_state row was created")
    summary = str(state["summary"])
    if "[context compacted]" not in summary:
        _fail("Compaction state exists but does not contain the compacted-context marker")
    if not state["last_summarized_id"]:
        _fail("Compaction did not record last_summarized_id")
    if persisted_rows >= expected_uncompacted_rows:
        _fail(
            "Persisted working_memory rows were not trimmed after compaction. "
            f"rows={persisted_rows}, uncompacted={expected_uncompacted_rows}",
        )

    history = memory.get_history()
    if not history or history[0]["role"] != "system":
        _fail("Compacted history does not prepend the session summary as a system message")
    if marker not in history[0]["content"]:
        _fail("Compaction summary does not include the oversized conversation marker")

    _ok("Auto-compaction threshold was exceeded and persisted context was trimmed")
    _info("auto_compact_threshold", warning_state["auto_compact_threshold"])
    _info("post_compact_token_usage", warning_state["token_usage"])
    _info("persisted rows", f"{persisted_rows} < {expected_uncompacted_rows}")
    _info("summary chars", len(summary))
    _info("turn_counter", state["turn_counter"])


async def _exercise_long_term_memory(memory_db: Path, user_id: str) -> None:
    long_term = AgentLongTermMemory(
        memory_db,
        user_id=user_id,
        agent_id="math_agent",
        project_id="router_memory_compaction_test",
    )
    long_term.clear()

    tool_response = await long_term.record_to_memory(
        thinking="The router memory test should remember deterministic facts.",
        content=[
            "router_memory_compaction_test 使用 math_agent 作为无网络依赖的确定性分支。",
            "短期记忆压缩成功后会在 history 开头注入 system summary。",
        ],
        memory_type="test_fact",
        tags=["router", "memory", "compaction"],
    )
    ids = (tool_response.metadata or {}).get("memory_ids", [])
    if len(ids) != 3:
        _fail(f"record_to_memory should return 3 ids, got {ids}")

    retrieved_tool = await long_term.retrieve_from_memory(["math_agent", "system summary"], limit=5)
    retrieved_text = "\n".join(block.text for block in retrieved_tool.content)
    if "math_agent" not in retrieved_text or "system summary" not in retrieved_text:
        _fail(f"retrieve_from_memory did not return the recorded facts:\n{retrieved_text}")

    developer_ids = await long_term.record(
        [
            Msg(name="tester", role="user", content="长期记忆 developer record 路径可写入。"),
        ],
        memory_type="developer_fact",
    )
    if len(developer_ids) != 1:
        _fail(f"record should return 1 id, got {developer_ids}")
    developer_retrieved = await long_term.retrieve(
        Msg(name="tester", role="user", content="developer record"),
        limit=3,
        memory_type="developer_fact",
    )
    if "developer record" not in developer_retrieved:
        _fail(f"retrieve did not find the developer-recorded memory:\n{developer_retrieved}")


def _step3_verify_long_term_memory(memory_db: Path, user_id: str) -> None:
    _banner("STEP 3  Verify AgentLongTermMemory functions")
    asyncio.run(_exercise_long_term_memory(memory_db, user_id))
    with _connect(memory_db) as conn:
        row_count = int(
            conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM long_term_memory
                WHERE user_id = ? AND project_id = ?
                """,
                (user_id, "router_memory_compaction_test"),
            ).fetchone()["count"],
        )
    if row_count < 4:
        _fail(f"Expected long_term_memory rows to be persisted, got {row_count}")
    _ok("Long-term memory record/retrieve and tool APIs are implemented")
    _info("long_term_memory rows", row_count)


def main() -> None:
    if not RUN_ROUTER_FLOW.exists():
        _fail(f"Missing workflow entrypoint: {RUN_ROUTER_FLOW}")

    os.environ["AGENT_AUTO_COMPACT_WINDOW"] = "34000"
    os.environ["AGENT_MAX_OUTPUT_TOKENS"] = "1000"
    user_id = f"router_memory_user_{uuid.uuid4().hex[:8]}"
    session_id = f"router_memory_session_{uuid.uuid4().hex[:8]}"

    memory_db = PROJECT_ROOT / "system_test" / f"_router_memory_test_{uuid.uuid4().hex}.sqlite3"
    try:
        _info("memory db", memory_db)
        _step1_verify_working_memory_connection(memory_db, user_id, session_id)
        _step2_trigger_short_term_compaction(memory_db, user_id, session_id)
        _step3_verify_long_term_memory(memory_db, user_id)
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            try:
                memory_db.with_name(memory_db.name + suffix).unlink(missing_ok=True)
            except PermissionError:
                pass

    _banner("Conclusion")
    _ok("RouterFlow, short-term compaction, context trimming, and long-term memory all passed")


if __name__ == "__main__":
    main()

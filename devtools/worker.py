"""Optional development workflow; never imported by the Discord bot."""
import argparse
import json
import os
import re
import time
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langgraph.checkpoint.sqlite import SqliteSaver

REPOSITORY = "keroeyes/discord-bot"
SHA = re.compile(r"[0-9a-f]{40}")
MAX_ATTEMPTS = 2

class WorkState(TypedDict):
    commit: str
    attempts: int
    status: str
    result: str

def validate_commit(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("A full lowercase commit SHA is required")
    return value

def test_in_e2b(commit, sandbox_factory=None):
    """Create one clean sandbox per attempt; return only an allowlisted result."""
    validate_commit(commit)
    key = os.getenv("E2B_API_KEY")
    if not key:
        return "missing_credentials"
    if sandbox_factory is None:
        from e2b import Sandbox
        sandbox_factory = Sandbox.create
    sandbox = None
    try:
        sandbox = sandbox_factory(api_key=key, timeout=300, secure=True)
        # No host environment, auth files, prompt text or memory is uploaded.
        command = (
            "git clone --quiet https://github.com/" + REPOSITORY + ".git /tmp/work"
            " && cd /tmp/work && git checkout --quiet --detach " + commit
            + " && python -m pip install -q -r requirements.txt"
            " && python -m unittest discover -s tests -v"
        )
        result = sandbox.commands.run(command, timeout=240)
        return "passed" if result.exit_code == 0 else "failed"
    except Exception:
        # Never persist raw output/exceptions, which may contain sensitive data.
        return "execution_error"
    finally:
        if sandbox is not None:
            try:
                sandbox.kill()
            except Exception:
                pass  # The sandbox's 300-second TTL still bounds its lifetime.

def build_graph(checkpointer, tester=test_in_e2b):
    def await_commit(state):
        value = interrupt({"action": "provide_test_commit", "attempt": state["attempts"] + 1})
        return {"commit": validate_commit(value), "status": "testing"}

    def test(state):
        # Checkpoint pending nodes can be replayed after a host crash.
        # Every replay uses a fresh sandbox; it never merges or deploys.
        result = tester(state["commit"])
        if result not in {"passed", "failed", "execution_error", "missing_credentials"}:
            result = "execution_error"
        attempts = state["attempts"] + 1
        status = "ready_for_pr" if result == "passed" else (
            "blocked" if result == "missing_credentials" else
            "exhausted" if attempts >= MAX_ATTEMPTS else "retry")
        return {"attempts": attempts, "result": result, "status": status}

    graph = StateGraph(WorkState)
    graph.add_node("await_commit", await_commit)
    graph.add_node("test", test)
    graph.add_edge(START, "await_commit")
    graph.add_edge("await_commit", "test")
    graph.add_conditional_edges("test", lambda s: "await_commit" if s["status"] == "retry" else END)
    return graph.compile(checkpointer=checkpointer)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="Private, persistent checkpoint file")
    parser.add_argument("--job", required=True, help="Unique work identifier")
    parser.add_argument("--commit", help="Resume with the agent's candidate commit")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.job):
        parser.error("Invalid job identifier")
    config = {"configurable": {"thread_id": args.job}, "recursion_limit": 12}
    with SqliteSaver.from_conn_string(args.db) as saver:
        graph = build_graph(saver)
        snapshot = graph.get_state(config)
        if args.commit:
            validate_commit(args.commit)
            if not snapshot.next:
                parser.error("Job is not waiting for a candidate commit")
            value = Command(resume=args.commit)
        else:
            if snapshot.values:
                print(json.dumps({"status": snapshot.values.get("status"), "pending": list(snapshot.next)}))
                return
            value = {"commit": "", "attempts": 0, "status": "awaiting_commit", "result": ""}
        result = graph.invoke(value, config)
        print(json.dumps({k: result[k] for k in ("attempts", "status", "result")}))
if __name__ == "__main__":
    main()

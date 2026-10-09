"""Allowlisted operational metadata only; never capture prompts, IDs or exceptions."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
from time import monotonic
from uuid import uuid4

log = logging.getLogger("bot.observability")
_current = ContextVar("bot_trace", default=None)
_client = None
_client_attempted = False
COMMANDS = {"!질문", "!기억", "!기억검색", "!기억삭제"}
PROVIDERS = {"openai", "subscription", "hindsight"}
STAGES = {"memory_recall", "memory_save", "memory_delete", "answer_generation", "delivery"}


def _safe_call(target, method, **kwargs):
    if target is None:
        return None
    try:
        return getattr(target, method)(**kwargs)
    except Exception:
        # A telemetry failure must neither expose data nor break the user's request.
        return None


def _get_client():
    global _client, _client_attempted
    if _client_attempted:
        return _client
    _client_attempted = True
    if os.getenv("BOT_LANGFUSE_ENABLED", "").strip().lower() not in {"1", "true"}:
        return None
    if not all(os.getenv(k, "").strip() for k in
               ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")):
        log.warning("Langfuse disabled: configuration incomplete")
        return None
    try:
        from langfuse import get_client
        _client = get_client()
    except Exception:
        log.warning("Langfuse disabled: SDK initialization failed")
    return _client


def record_search(search_count, source_count):
    trace = _current.get()
    if trace is not None:
        trace["search_count"] = search_count
        trace["source_count"] = source_count
        trace["search_state"] = ("not_observed" if search_count == 0 else
                                 "sources_missing" if source_count == 0 else "sources_present")


def record_memory(count):
    trace = _current.get()
    if trace is not None:
        trace["memory_count"] = count


def mark_delivery_failed():
    trace = _current.get()
    if trace is not None:
        trace["delivery"] = "failed"


@contextmanager
def request_trace(command, provider):
    record = {
        "schema_version": 1, "request_id": uuid4().hex,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "command": command if command in COMMANDS else "other",
        "provider": provider if provider in PROVIDERS else "other",
        "status": "running", "search_state": "not_observed",
        "search_count": None, "source_count": None, "memory_count": None,
        "delivery": "not_attempted", "stages": [],
    }
    root = _safe_call(_get_client(), "start_observation",
                      name="discord.request", as_type="span",
                      metadata={"request_id": record["request_id"],
                                "command": record["command"], "provider": record["provider"]})
    record["_span"] = root
    token = _current.set(record)
    started = monotonic()
    try:
        yield record
    except BaseException:
        record["status"] = "failed"
        raise
    else:
        record["status"] = ("delivery_failed" if record["delivery"] == "failed" else
                            "degraded" if any(s["status"] == "failed" for s in record["stages"])
                            else "completed")
    finally:
        record["duration_ms"] = max(0, round((monotonic() - started) * 1000))
        record.pop("_span", None)
        _current.reset(token)
        _safe_call(root, "update", metadata=record,
                   level="ERROR" if record["status"] in {"failed", "delivery_failed"} else "DEFAULT")
        _safe_call(root, "end")
        try:
            log.info("bot_trace %s", json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        except Exception:
            pass


@contextmanager
def stage(name):
    if name not in STAGES:
        raise ValueError("Unknown telemetry stage")
    trace = _current.get()
    started = monotonic()
    span = _safe_call(trace.get("_span") if trace else None,
                      "start_observation", name=name, as_type="span")
    outcome = "completed"
    try:
        yield
    except BaseException:
        outcome = "failed"
        raise
    finally:
        if trace is not None and name == "delivery" and trace["delivery"] == "failed":
            outcome = "failed"
        item = {"name": name, "status": outcome,
                "duration_ms": max(0, round((monotonic() - started) * 1000))}
        if trace is not None:
            trace["stages"].append(item)
            if name == "delivery" and trace["delivery"] != "failed":
                trace["delivery"] = outcome
        _safe_call(span, "update", metadata=item,
                   level="ERROR" if outcome == "failed" else "DEFAULT")
        _safe_call(span, "end")


def flush():
    _safe_call(_client, "flush")

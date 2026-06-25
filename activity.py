"""In-memory, thread-safe activity feed for background processes.

Discovery runs across background threads + a ThreadPoolExecutor, matching and backup run in
request handlers / subprocesses. They all report progress here so the UI can show a detailed,
live, refresh-persistent view of what's happening (which board/company is being fetched or
matched, whether a DB snapshot/commit/push is in flight, etc.).

State is process-memory only (lost on server restart) — that's fine; durable counters like
discovery_last_run already live in kv_store.
"""

from __future__ import annotations

import itertools
import threading
from collections import deque
from datetime import datetime, timezone

_lock = threading.Lock()
_tasks: dict[str, dict] = {}
_recent: "deque[dict]" = deque(maxlen=20)   # finished tasks, newest-first kept for brief display
_events: "deque[dict]" = deque(maxlen=300)  # rolling log lines, newest appended
_ids = itertools.count(1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start(kind: str, label: str, total: int | None = None) -> str:
    """Begin a task. Returns an id to pass to update()/finish()."""
    task_id = f"{kind}-{next(_ids)}"
    with _lock:
        _tasks[task_id] = {
            "id": task_id,
            "kind": kind,
            "label": label,
            "detail": "",
            "current": 0,
            "total": total,
            "status": "running",
            "started_at": _now(),
            "updated_at": _now(),
        }
    log(kind, f"{label} started")
    return task_id


def update(task_id: str, detail: str | None = None, current: int | None = None,
           total: int | None = None, advance: bool = False, log_it: bool = True) -> None:
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        if detail is not None:
            t["detail"] = detail
        if total is not None:
            t["total"] = total
        if advance:
            t["current"] = (t["current"] or 0) + 1
        elif current is not None:
            t["current"] = current
        t["updated_at"] = _now()
        kind = t["kind"]
    if log_it and detail:
        log(kind, detail)


def finish(task_id: str, summary: str | None = None, status: str = "done") -> None:
    with _lock:
        t = _tasks.pop(task_id, None)
        if not t:
            return
        t["status"] = status
        t["finished_at"] = _now()
        if summary:
            t["detail"] = summary
        _recent.appendleft(t)
        kind, label = t["kind"], t["label"]
    log(kind, f"{label} finished" + (f" — {summary}" if summary else ""))


def log(kind: str, msg: str) -> None:
    if not msg:
        return
    with _lock:
        _events.append({"ts": _now(), "kind": kind, "msg": msg})


def snapshot() -> dict:
    with _lock:
        tasks = sorted(_tasks.values(), key=lambda t: t["started_at"])
        return {
            "ts": _now(),
            "tasks": [dict(t) for t in tasks],
            "recent": [dict(t) for t in list(_recent)[:5]],
            "events": [dict(e) for e in reversed(_events)],  # newest first
        }


def clear() -> None:
    """Reset everything (used by tests)."""
    with _lock:
        _tasks.clear()
        _recent.clear()
        _events.clear()

"""
In-process job registry for long-running research runs.

The research pipeline takes minutes. Holding an HTTP request open for that long
gives the browser nothing to render, so runs are submitted as jobs: the route
returns a job id immediately and the client subscribes to a Server-Sent Events
stream for stage-by-stage progress.

State lives in memory only — a restart drops running jobs, which is acceptable
for a single-process dev/demo deployment. Swap `JobRegistry` for a Redis-backed
implementation if this ever runs multi-worker.
"""
import json
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Terminal item pushed onto a job's queue so SSE generators know to stop.
_SENTINEL = object()

# How long a finished job's result stays retrievable.
JOB_TTL_SECONDS = 3600

# Ordered pipeline stages, mirrored by the UI so cards can render before the
# first event arrives.
STAGES = [
    (1, "Topic Expansion"),
    (2, "Paper Discovery"),
    (3, "Claim Extraction"),
    (4, "Claim Normalization"),
    (5, "Contradiction Detection"),
    (6, "Research Gap Detection"),
    (7, "Citation Building"),
    (8, "Recommendations"),
    (9, "Storing in Memory"),
]

# Literature Builder v2 continues the same numbered stream: 1-9 are the research
# pipeline above, 10-17 are the evidence-table/synthesis/narrative pipeline.
LITERATURE_STAGES = STAGES + [
    (10, "Classify Papers"),
    (11, "Evidence Extraction"),
    (12, "Bibliography"),
    (13, "Cluster Claims"),
    (14, "Synthesis Matrix"),
    (15, "Outline"),
    (16, "Narrative Generation"),
    (17, "PRISMA Counts"),
]


class ResearchCancelled(Exception):
    """Raised inside the pipeline when the client cancels a run."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Job:
    """One research run: its status, its event history, and its result."""

    def __init__(self, job_id: str, topic: str):
        self.id = job_id
        self.topic = topic
        self.status = "queued"          # queued | running | done | error | cancelled
        self.created_at = datetime.now(timezone.utc)
        self.finished_at: Optional[datetime] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None

        self._seq = 0
        self._events: List[Dict[str, Any]] = []
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()
        self.cancel_event = threading.Event()

    # ── event fan-out ───────────────────────────────────────────────────────
    def emit(self, event_type: str, **payload) -> Dict[str, Any]:
        """Record an event and push it to every live subscriber."""
        with self._lock:
            self._seq += 1
            event = {"seq": self._seq, "type": event_type, "ts": _now(), **payload}
            self._events.append(event)
            subscribers = list(self._subscribers)
        for sub in subscribers:
            sub.put(event)
        return event

    def subscribe(self) -> queue.Queue:
        """Get a queue pre-loaded with events so far, then fed live ones.

        Replaying history means a client that connects late — or reconnects —
        still sees every stage rather than joining mid-run with blank cards.
        """
        q: queue.Queue = queue.Queue()
        with self._lock:
            for event in self._events:
                q.put(event)
            if self.status in ("done", "error", "cancelled"):
                q.put(_SENTINEL)
            else:
                self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def close(self) -> None:
        """Signal every subscriber that no further events are coming."""
        with self._lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for sub in subscribers:
            sub.put(_SENTINEL)

    # ── lifecycle ───────────────────────────────────────────────────────────
    def cancel(self) -> None:
        self.cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check_cancelled(self) -> None:
        """Raise if the client asked to stop. Called between pipeline stages."""
        if self.cancel_event.is_set():
            raise ResearchCancelled("Research cancelled by user")

    def finish(self, status: str, result=None, error: Optional[str] = None) -> None:
        self.status = status
        self.result = result
        self.error = error
        self.finished_at = datetime.now(timezone.utc)
        self.emit("end", status=status, error=error)
        self.close()

    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()

    def summary(self) -> Dict[str, Any]:
        return {
            "job_id": self.id,
            "topic": self.topic,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "error": self.error,
        }


class JobRegistry:
    """Thread-safe job store with TTL cleanup on write."""

    def __init__(self, ttl_seconds: int = JOB_TTL_SECONDS):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def create(self, topic: str) -> Job:
        job = Job(uuid.uuid4().hex, topic)
        with self._lock:
            self._prune_locked()
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def _prune_locked(self) -> None:
        stale = [
            jid for jid, job in self._jobs.items()
            if job.status in ("done", "error", "cancelled") and job.age_seconds() > self._ttl
        ]
        for jid in stale:
            del self._jobs[jid]


# Module-level singleton used by the Flask routes.
JOBS = JobRegistry()


def sse_format(event: Dict[str, Any]) -> str:
    """Serialize one event as an SSE frame."""
    return f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"


def is_sentinel(item: Any) -> bool:
    return item is _SENTINEL

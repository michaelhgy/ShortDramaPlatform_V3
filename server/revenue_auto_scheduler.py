"""Persisted V2 revenue auto-collection schedule.

This scheduler does not contain provider rules. It only decides when to call
the existing revenue collector and records which configured slots one run
covered, so a restart never replays the same missed slot repeatedly.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta

from server import v2_file_service as service
from server.revenue_collection_state import SHANGHAI


_STOP = threading.Event()
_STARTED = False
_START_LOCK = threading.Lock()


def _automatic_slots_already_run(conn, run_date: str) -> set[str]:
    rows = conn.execute(
        """SELECT scheduled_slots_json FROM v2_revenue_collection_runs
           WHERE trigger_source='automatic' AND substr(created_at, 1, 10)=?""",
        (run_date,),
    ).fetchall()
    slots: set[str] = set()
    for row in rows:
        try:
            value = json.loads(str(row["scheduled_slots_json"] or "[]"))
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            slots.update(item for item in value if isinstance(item, str))
    return slots


def run_due_auto_collection(now: datetime | None = None) -> dict[str, object] | None:
    """Run one catch-up for all missed slots, or the single current slot.

    The existing immediate-collection UI uses the prior calendar day. The
    automatic path deliberately invokes that same single-date behavior.
    """
    current = now or datetime.now(SHANGHAI)
    current = current.replace(tzinfo=SHANGHAI) if current.tzinfo is None else current.astimezone(SHANGHAI)
    settings = service.get_v2_settings()
    if not bool(settings["revenue_auto_collection_enabled"]):
        return None
    configured = settings["revenue_auto_collection_times"]
    if not isinstance(configured, list):
        return None
    slots = sorted(item for item in configured if isinstance(item, str))
    clock = current.strftime("%H:%M")
    due_slots = [slot for slot in slots if slot <= clock]
    if not due_slots:
        return None
    today = current.date().isoformat()
    conn = service.connection()
    try:
        active = conn.execute(
            "SELECT 1 FROM v2_revenue_collection_runs WHERE status IN ('queued', 'running') LIMIT 1"
        ).fetchone()
        if active:
            return None
        completed_slots = _automatic_slots_already_run(conn, today)
    finally:
        conn.close()
    missed_slots = [slot for slot in due_slots if slot not in completed_slots]
    if not missed_slots:
        return None
    revenue_day = (current.date() - timedelta(days=1)).isoformat()
    return service.start_revenue_collection(
        revenue_day,
        revenue_day,
        trigger_source="automatic",
        scheduled_slots=missed_slots,
    )


def _loop() -> None:
    while True:
        try:
            run_due_auto_collection()
        except Exception:
            # A later check can retry scheduling; collector failures are
            # persisted on their own run record by the shared entry point.
            pass
        if _STOP.wait(15):
            return


def start_revenue_auto_scheduler() -> None:
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return
        _STARTED = True
        threading.Thread(target=_loop, name="v2-revenue-auto-scheduler", daemon=True).start()

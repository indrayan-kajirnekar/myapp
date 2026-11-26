"""
scheduler.py — APScheduler-based email report scheduler for HyperMonitor.

Supported schedule types (all evaluated in a configurable IANA timezone,
default "UTC"):
  • "daily"    — every day at HH:MM
  • "weekly"   — every week on a fixed day (0=Mon … 6=Sun) at HH:MM
  • "monthly"  — every month on a fixed day (1-28, or 0 = last day) at HH:MM
  • "custom"   — a user supplied 5-field cron expression
                 (minute hour day-of-month month day-of-week)

The schedule is persisted in the email_schedule table (one row, id=1).
APScheduler stores jobs in memory only — the app re-registers from DB on
startup.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Lazy APScheduler init
# ──────────────────────────────────────────────────────────────────────────────

_scheduler = None   # type: ignore


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

JOB_ID = "scheduled_report"
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def start() -> None:
    sched = _get_scheduler()
    if not sched.running:
        sched.start()
        log.info("APScheduler started.")


def stop() -> None:
    sched = _get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        log.info("APScheduler stopped.")


def remove_job() -> None:
    sched = _get_scheduler()
    if sched.get_job(JOB_ID):
        sched.remove_job(JOB_ID)
        log.info("Scheduled report job removed.")


def validate_timezone(tz: str) -> None:
    """Raise ValueError if tz is not a known IANA timezone name."""
    from apscheduler.util import astimezone
    try:
        if astimezone(tz) is None:
            raise ValueError
    except Exception:
        raise ValueError(f"Unknown timezone '{tz}'.")


def validate_cron(expr: str, tz: str = "UTC") -> None:
    """Raise ValueError if expr is not a valid 5-field cron expression."""
    from apscheduler.triggers.cron import CronTrigger
    try:
        CronTrigger.from_crontab(expr, timezone=tz)
    except Exception as exc:
        raise ValueError(f"Invalid cron expression '{expr}': {exc}")


def _add(trigger, job_fn: Callable, grace: int) -> None:
    sched = _get_scheduler()
    remove_job()
    sched.add_job(
        job_fn,
        trigger=trigger,
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=grace,
        coalesce=True,
    )


def schedule_daily(hour: int, minute: int, job_fn: Callable,
                   tz: str = "UTC") -> None:
    """Run job_fn every day at HH:MM in timezone tz."""
    from apscheduler.triggers.cron import CronTrigger
    _add(CronTrigger(hour=hour, minute=minute, timezone=tz), job_fn, 300)
    log.info("Daily report scheduled at %02d:%02d %s", hour, minute, tz)


def schedule_weekly(day_of_week: int, hour: int, minute: int,
                    job_fn: Callable, tz: str = "UTC") -> None:
    """Run job_fn every week. day_of_week: 0=Monday … 6=Sunday."""
    from apscheduler.triggers.cron import CronTrigger
    day = _DAYS[day_of_week % 7]
    _add(CronTrigger(day_of_week=day, hour=hour, minute=minute, timezone=tz),
         job_fn, 600)
    log.info("Weekly report scheduled on %s at %02d:%02d %s",
             day, hour, minute, tz)


def schedule_monthly(day_of_month: int, hour: int, minute: int,
                     job_fn: Callable, tz: str = "UTC") -> None:
    """Run job_fn every month. day_of_month: 1-28, or 0 for the last day."""
    from apscheduler.triggers.cron import CronTrigger
    day = "last" if day_of_month == 0 else day_of_month
    _add(CronTrigger(day=day, hour=hour, minute=minute, timezone=tz),
         job_fn, 3600)
    log.info("Monthly report scheduled on day %s at %02d:%02d %s",
             day, hour, minute, tz)


def schedule_custom(cron_expr: str, job_fn: Callable, tz: str = "UTC") -> None:
    """Run job_fn according to a 5-field cron expression."""
    from apscheduler.triggers.cron import CronTrigger
    _add(CronTrigger.from_crontab(cron_expr, timezone=tz), job_fn, 600)
    log.info("Custom report scheduled with cron '%s' (%s)", cron_expr, tz)


def get_next_run() -> Optional[str]:
    """Return ISO-8601 string of the next scheduled run, or None."""
    sched = _get_scheduler()
    job = sched.get_job(JOB_ID)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None

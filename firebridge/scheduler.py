from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Callable
from zoneinfo import ZoneInfo

from tools.adb import AdbRunner

from .config import AppConfig
from .cron import CronExpression, parse_cron_expression
from .logging import get_logger, truncate
from .workflow import Publisher, WorkflowResult, WorkflowRunner
from .yaml_endpoints import EndpointConfig

log = get_logger("firebridge.scheduler")


NowProvider = Callable[[], datetime]


@dataclass
class ScheduledWorkflow:
    endpoint: EndpointConfig
    cron: CronExpression
    timezone: ZoneInfo
    payload: str
    run_on_start_pending: bool
    next_run: datetime

    @classmethod
    def from_endpoint(
        cls,
        config: AppConfig,
        endpoint: EndpointConfig,
        now: datetime,
    ) -> "ScheduledWorkflow | None":
        if endpoint.schedule is None:
            return None

        timezone = ZoneInfo(endpoint.schedule.timezone or config.timezone)
        current_time = now.astimezone(timezone)
        cron = parse_cron_expression(endpoint.schedule.cron)
        return cls(
            endpoint=endpoint,
            cron=cron,
            timezone=timezone,
            payload=endpoint.schedule.payload,
            run_on_start_pending=endpoint.schedule.run_on_start,
            next_run=cron.next_after(current_time),
        )

    def is_due(self, now: datetime) -> bool:
        if self.run_on_start_pending:
            return True
        return now.astimezone(self.timezone) >= self.next_run

    def mark_run(self, now: datetime) -> None:
        self.run_on_start_pending = False
        self.next_run = self.cron.next_after(now.astimezone(self.timezone))


class WorkflowScheduler:
    def __init__(
        self,
        config: AppConfig,
        endpoints: list[EndpointConfig],
        runner: AdbRunner,
        publisher: Publisher | None = None,
        adb_lock: RLock | None = None,
        now: NowProvider | None = None,
    ) -> None:
        self.config = config
        self.runner = runner
        self.publisher = publisher
        self.adb_lock = adb_lock or RLock()
        self.now = now or (lambda: datetime.now(ZoneInfo(config.timezone)))
        current_time = self.now()
        self.jobs: list[ScheduledWorkflow] = []
        for endpoint in endpoints:
            job = ScheduledWorkflow.from_endpoint(config, endpoint, current_time)
            if job is not None:
                self.jobs.append(job)
        if self.jobs:
            log.info(
                "Scheduler armed",
                extra={
                    "jobs": len(self.jobs),
                    "endpoints": [job.endpoint.id for job in self.jobs],
                },
            )

    def run_due(self) -> list[WorkflowResult]:
        current_time = self.now()
        results: list[WorkflowResult] = []
        for job in self.jobs:
            if not job.is_due(current_time):
                continue

            log.debug(
                "Scheduled workflow due",
                extra={
                    "endpoint_id": job.endpoint.id,
                    "cron": job.cron.expression,
                },
            )
            started = time.monotonic()
            with self.adb_lock:
                workflow = WorkflowRunner(
                    self.config,
                    self.runner,
                    publisher=self.publisher,
                )
                result = workflow.run(job.endpoint, job.payload)
            duration_ms = int((time.monotonic() - started) * 1000)
            log.info(
                "Scheduled workflow finished",
                extra={
                    "endpoint_id": job.endpoint.id,
                    "status": result.status,
                    "return_value": truncate(result.return_value, 120),
                    "commands": len(result.commands),
                    "duration_ms": duration_ms,
                },
            )
            self._publish_return_state(job.endpoint, result)
            job.mark_run(current_time)
            results.append(result)

        return results

    def _publish_return_state(
        self,
        endpoint: EndpointConfig,
        result: WorkflowResult,
    ) -> None:
        if self.publisher is None or result.return_value is None:
            return

        state_topic = endpoint.state_topic(self.config)
        if not state_topic:
            return

        already_published = any(publish.topic == state_topic for publish in result.publishes)
        if not already_published:
            self.publisher(state_topic, str(result.return_value), True)

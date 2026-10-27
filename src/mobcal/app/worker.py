"""The worker thread: one batch handed to ``mobcal.run.run_many``, reported back by signals.

The driver's callbacks arrive on its supervising threads; each re-emits as a Qt signal, which
Qt queues onto the UI thread, so the window draws only there. ``stop`` is the driver's
``Stop``: safe from the UI thread, it kills every process of the batch with its whole tree and
the runs it ended come back as stopped. The summary is written by the worker, not the window,
since it reads every record in the results folder.
"""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from mobcal import estimate
from mobcal.batch import CLASH, Batch, prior
from mobcal.run import Job, Launcher, Result, Stop, run_many


class BatchWorker(QThread):
    planned = Signal(object)  # the estimate.Plan the batch runs to
    run_started = Signal(object)  # Job
    run_landed = Signal(object, int, int)  # Result, how many landed, how many there are
    blocks = Signal(object, int, int)  # Job, blocks written, blocks expected (split runs)
    finished_batch = Signal(object)  # mobcal.run.Summary, once summary.csv/json are written
    failed = Signal(str)  # the batch could not run at all

    def __init__(self, batch: Batch, sizes: dict | None = None,
                 launcher: Launcher | None = None, cpus: int | None = None) -> None:
        super().__init__()
        self.batch = batch
        self._sizes = dict(sizes or {})
        self._launcher = launcher
        self._cpus = cpus
        self._stop = Stop()

    def stop(self) -> None:
        self._stop()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def run(self) -> None:  # QThread's entry point, on the worker thread
        try:
            jobs = self.batch.to_run()
            clashes = [p for p in prior(jobs) if p.kind == CLASH]
            if clashes:
                self.failed.emit("; ".join(f"{p.job.run_dir.name} {p.detail}" for p in clashes))
                return
            if not jobs:
                self.failed.emit("nothing to run: the folder holds every run of this batch "
                                 "complete")
                return
            plan: estimate.Plan = self.batch.plan(self._cpus, jobs=jobs, sizes=self._sizes)
            self.planned.emit(plan)
            summary = run_many(plan.jobs, plan.workers, progress=self._landed,
                               launcher=self._launcher, blocks=self._blocks,
                               stop=self._stop, on_start=self._started)
            summary.write(self.batch.out_dir)
            self.finished_batch.emit(summary)
        except Exception as e:  # anything else is a bug, shown rather than lost with the thread
            self.failed.emit(f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=4)}")

    def _started(self, job: Job) -> None:
        self.run_started.emit(job)

    def _landed(self, r: Result, done: int, total: int) -> None:
        self.run_landed.emit(r, done, total)

    def _blocks(self, job: Job, n: int, total: int) -> None:
        self.blocks.emit(job, n, total)

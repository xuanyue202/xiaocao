"""KOL support inside the original paper rendezvous, outside ledger writes."""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from xiaocao.kol import opening_preparation as preparation
from xiaocao.kol.trading_context import TradingContextError, build_trading_context, write_trading_projection
from xiaocao.kol.trading_decision import read_json
from xiaocao.runner_recovery import _write
from xiaocao.utils.trading_session import A_SHARE_TZ
from . import kol_policy, paper_decision_support as paper
from .morning_bundle import read_consumed_rows
from .runtime_snapshot import operational_root


def owner_binding(run_dir: Path, date: str) -> dict:
    manifest = read_json(run_dir / "manifest.json")
    binding = {"trade_date": date, "automation_id": manifest.get("automation_id"),
               "owner_thread_id": manifest.get("thread_id"), "run_id": manifest.get("run_id")}
    if (manifest.get("market_date") != date or manifest.get("run_id") != run_dir.name
            or binding["automation_id"] != "xiaocao-daily-morning-execution"
            or binding["automation_id"] != os.environ.get("CODEX_AUTOMATION_ID")
            or not binding["owner_thread_id"] or binding["owner_thread_id"] != os.environ.get("CODEX_THREAD_ID")):
        raise ValueError("PAPER_KOL_ORIGINAL_OWNER_REQUIRED")
    return binding


def write_once(path: Path, value: dict) -> None:
    if path.exists():
        if path.is_symlink() or read_json(path) != value:
            raise ValueError("PAPER_KOL_IMMUTABILITY_VIOLATION")
    else:
        _write(path, value)


def register_preparation(root: Path, path: Path, prepared: dict) -> None:
    """Original parent publishes only its own pre-09:20 support reference."""
    binding = prepared["binding"]
    run_id = binding["run_id"]
    if Path(run_id).name != run_id:
        raise ValueError("PAPER_KOL_RUN_ID_INVALID")
    run_dir = root / "output/live/auto/runs" / run_id
    if owner_binding(run_dir, binding["trade_date"]) != binding:
        raise ValueError("PAPER_KOL_PREPARATION_OWNER_MISMATCH")
    write_once(run_dir / "kol-preparation.json", {"binding": binding,
        "preparation_path": str(path.resolve()), "preparation_sha256": prepared["preparation_sha256"]})


def _read_account_preview(root: Path) -> tuple[dict, dict]:
    """Read/mark consistent paper B facts; no risk-head or account writes."""
    from xiaocao.api.client import XiaocaoClient
    def read():
        account = read_json(root / "output/live/paper_account.json")
        positions = paper.read_paper_positions(root / "output/live/positions.jsonl")
        return account, positions
    with paper.paper_ledger_lock(root):
        account, positions = read()
    initial_hash = preparation.canonical_sha256([account, positions])
    marks = paper.fetch_paper_marks(XiaocaoClient(timeout=3, retries=0), positions)
    with paper.paper_ledger_lock(root):
        current = read()
        if preparation.canonical_sha256(list(current)) != initial_hash:
            raise ValueError("PAPER_KOL_ACCOUNT_CHANGED_DURING_MARKS")
        observed = datetime.now(A_SHARE_TZ)
        risk = paper.evaluate_paper_risk(root, account, positions, now=observed,
                                       mark_provider=lambda code: marks.get(code, {}), persist=False)
    return {"account": account, "positions": positions, "marks": marks,
            "observed_at": observed.isoformat(), "authority": "preview_only"}, risk


class _PreviewTerminated(BaseException):
    pass


def account_preview(root: Path, *, deadline: datetime) -> tuple[dict, dict]:
    """Bound locks, market reads and their helper children to the original wait.

    The disposable process only reads account state and evaluates persist=False.
    An isolated process group lets timeout cleanup include Keychain helpers,
    while the original supervisor/writer and its leases remain untouched.
    """
    remaining = (deadline - datetime.now(A_SHARE_TZ)).total_seconds()
    if remaining <= 0:
        raise ValueError("PAPER_KOL_PREVIEW_DEADLINE")
    previous = signal.getsignal(signal.SIGTERM)
    if previous != signal.SIG_DFL:
        raise ValueError("PAPER_KOL_PREVIEW_OWNER_SIGNAL_HANDLER_UNSUPPORTED")
    def terminate(signum, frame):
        raise _PreviewTerminated()
    # Block termination only across child creation/handler installation. The
    # child unblocks it at startup; there is no launch-to-registration orphan gap.
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
    try:
        with subprocess.Popen([sys.executable, "-m", __name__, str(root.resolve()), deadline.isoformat()],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True) as child:
            try:
                signal.signal(signal.SIGTERM, terminate)
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
                stdout, _ = child.communicate(timeout=max(0, (deadline - datetime.now(A_SHARE_TZ)).total_seconds()))
            except BaseException as exc:
                # Only this read-only child's newly created group, never our owner.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.communicate()
                if isinstance(exc, _PreviewTerminated):
                    signal.signal(signal.SIGTERM, previous)
                    signal.raise_signal(signal.SIGTERM)
                if isinstance(exc, subprocess.TimeoutExpired):
                    raise ValueError("PAPER_KOL_PREVIEW_DEADLINE") from None
                raise
            if datetime.now(A_SHARE_TZ) >= deadline:
                raise ValueError("PAPER_KOL_PREVIEW_DEADLINE")
            if child.returncode:
                raise ValueError("PAPER_KOL_PREVIEW_UNAVAILABLE")
    finally:
        signal.signal(signal.SIGTERM, previous)
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
    facts, risk = json.loads(stdout)
    if facts.get("authority") != "preview_only" or risk.get("authority") != "preview_only":
        raise ValueError("PAPER_KOL_PREVIEW_AUTHORITY_INVALID")
    return facts, risk


class PaperKolReview:
    """One support state machine driven by the original intelligence wait loop."""
    def __init__(self, root: Path, run_dir: Path, date: str, freeze: dict,
                 *, now=None, preview=account_preview, emit=None, budget_seconds=120.0):
        self.root, self.run_dir, self.date = root, run_dir, date
        self.now = now or (lambda: datetime.now(A_SHARE_TZ))
        self.emit = emit or (lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))
        self.path = run_dir / "paper-kol-review.receipt.json"
        self.binding = owner_binding(run_dir, date)
        self.freeze = freeze
        self.request = None
        self.receipt = None
        if self.path.exists():
            self.receipt = read_support(self.path, date, freeze, run_dir)
            return
        self.started = self.now()
        if not math.isfinite(budget_seconds) or budget_seconds < 0:
            raise ValueError("PAPER_KOL_INVALID_ORIGINAL_BUDGET")
        self.cutoff = min(self.started + timedelta(seconds=min(120, budget_seconds)),
                          datetime.fromisoformat(date + "T09:27:00+08:00"))
        try:
            self._start(preview)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            reason = str(exc) if isinstance(exc, TradingContextError) or str(exc).startswith(("PAPER_KOL_", "KOL_PREPARATION_")) else type(exc).__name__
            self._finish("deferred", "PAPER_KOL_SUPPORT_UNAVAILABLE:" + reason)

    def _start(self, preview):
        if self.now() >= self.cutoff:
            self._finish("deferred", "PAPER_KOL_CUTOFF_REACHED")
            return
        ready = read_json(self.run_dir / "kol-preparation.json")
        prepared = preparation.read_preparation(Path(ready["preparation_path"]), now=self.now())
        if (ready["binding"] != self.binding or prepared["binding"] != self.binding
                or ready["preparation_sha256"] != prepared["preparation_sha256"]):
            raise ValueError("PAPER_KOL_PREPARATION_OWNER_MISMATCH")
        state_root = operational_root(self.root)
        summary = write_trading_projection(build_trading_context(repo_root=state_root,
            read_report_ids=[], include_report_bodies=False,
            history_fresh_through=self.date + "T11:30:00+08:00"), repo_root=state_root)
        inputs = preparation.input_payload(summary, binding=self.binding, repo_root=state_root)
        input_path = preparation.write_artifact(self.run_dir, inputs, ".kol-inputs.json")
        facts, risk = preview(self.root, deadline=self.cutoff)
        if self.now() >= self.cutoff:
            raise ValueError("PAPER_KOL_PREVIEW_DEADLINE")
        if risk["deploy_factor"] <= 0:
            self._finish("not_required", "PAPER_ACCOUNT_RISK_BLOCKS_BUY")
            return
        rows = read_consumed_rows(self.freeze, self.date, live_dir=self.root / "output/live")
        request = {"trade_date": self.date, "runtime": "paper", "binding": self.binding,
            "requested_at": self.started.isoformat(), "review_wait_until": self.cutoff.isoformat(),
            "entry_deadline": self.cutoff.isoformat(), "max_wait_seconds": max(0, (self.cutoff-self.started).total_seconds()),
            "freeze_sha256": self.freeze["snapshot_sha256"], "freeze": self.freeze,
            "strategy_sha": self.freeze["strategy_sha"], "candidates": rows,
            "account_facts": facts, "account_risk": risk}
        request = preparation.normalized_review_facts(request)
        packet = preparation.opening_packet(Path(ready["preparation_path"]), input_path, request, now=self.now())
        packet_path = preparation.write_artifact(self.run_dir, packet, ".kol-packet.json")
        request["kol_inputs"] = {"packet_path": str(packet_path), "packet_sha256": packet["packet_sha256"],
            "warm_worker": prepared["worker_id"], "input_path": str(input_path)}
        request["dispatch_budget"] = {"observed_at": self.now().isoformat(),
            "total_remaining_seconds": max(0, (self.cutoff-self.now()).total_seconds()),
            "cutoff": self.cutoff.isoformat(), "includes": ["model", "source_verification", "independent_review", "publication"]}
        digest = kol_policy.decision_sha256(request)
        self.request = {**request, "request_sha256": digest}
        path = self.run_dir / (digest + ".paper-kol-request.json")
        write_once(path, self.request)
        from .morning_dispatch import write_warm_dispatch
        dispatch_path = write_warm_dispatch(self.request, path, now=self.now())
        self.emit({"event": "paper_kol_review_requested", "trade_date": self.date,
                   "request_path": str(path), "request_sha256": digest,
                   "dispatch_path": str(dispatch_path) if dispatch_path else None})

    def _finish(self, status: str, reason: str, policy=None):
        completed = self.now()
        value = {"schema_version": "paper-morning-kol-review.v1", "binding": self.binding,
            "trade_date": self.date, "freeze_sha256": self.freeze["snapshot_sha256"],
            "checkpoint_sha256": self.freeze.get("checkpoint_sha256"), "status": status, "reason": reason,
            "request_sha256": (self.request or {}).get("request_sha256"),
            "requested_at": self.started.isoformat(), "completed_at": completed.isoformat(),
            "entry_deadline": self.cutoff.isoformat(), "max_wait_seconds": max(0, (self.cutoff-self.started).total_seconds()),
            "waited_seconds": max(0, (completed-self.started).total_seconds()),
            "decision_sha256": (policy or {}).get("decision_sha256")}
        self.receipt = {**value, "receipt_sha256": kol_policy.decision_sha256(value)}
        write_once(self.path, self.receipt)

    def defer(self, reason: str) -> None:
        if self.receipt is None:
            self._finish("deferred", reason)

    def tick(self) -> bool:
        if self.receipt is not None:
            return True
        now = self.now()
        if now >= self.cutoff:
            self._finish("timed_out", "PAPER_KOL_ORIGINAL_CUTOFF")
            return True
        policy = kol_policy.load_decision(self.root / "output/live/kol_policy/decisions", "B", "paper", now)
        if policy["status"] == "validated":
            record = policy["record"]
            old = preparation.aware(record["decision"]["as_of"]) < self.started
            bound = all(record[key].get("morning_request_sha256") == self.request["request_sha256"]
                        for key in ("decision", "review"))
            if old or bound:
                if self.now() >= self.cutoff:
                    self._finish("timed_out", "PAPER_KOL_ORIGINAL_CUTOFF")
                    return True
                self._finish("validated", "REUSED_VALID_POLICY" if old else "PAPER_KOL_CURRENT_REQUEST_COMPLETED", policy)
                return True
        return False


def read_support(path: Path, date: str, freeze: dict, run_dir: Path) -> dict:
    value = read_json(path)
    if (path.resolve() != (run_dir / "paper-kol-review.receipt.json").resolve()
            or value.get("receipt_sha256") != kol_policy.decision_sha256({k:v for k,v in value.items() if k != "receipt_sha256"})
            or value.get("binding") != owner_binding(run_dir, date)
            or value.get("freeze_sha256") != freeze["snapshot_sha256"]
            or value.get("checkpoint_sha256") != freeze.get("checkpoint_sha256")):
        raise ValueError("PAPER_KOL_SUPPORT_RECEIPT_MISMATCH")
    return value


if __name__ == "__main__":
    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})
    remaining = (preparation.aware(sys.argv[2]) - datetime.now(A_SHARE_TZ)).total_seconds()
    if remaining <= 0 or os.getpgrp() != os.getpid():
        raise SystemExit(2)
    # Also self-limit if the original owner dies without a catchable signal.
    signal.signal(signal.SIGALRM, lambda *_: os.killpg(os.getpgrp(), signal.SIGKILL))
    signal.setitimer(signal.ITIMER_REAL, remaining)
    print(json.dumps(_read_account_preview(Path(sys.argv[1])), ensure_ascii=False, allow_nan=False))

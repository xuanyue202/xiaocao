"""Validate completed original EOD receipts before its final digest and handoff."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

from xiaocao.research import eod_feedback
from xiaocao.live.eod_post_business import COMMANDS


def closeout(root: Path, review: dict, *, env: Mapping[str, str],
             build_digest: Callable, push_digest: Callable | None = None) -> dict:
    """No APP query, business subprocess, settlement or historical receipt repair."""
    if (env.get("CODEX_AUTOMATION_ID") != eod_feedback.AUTOMATION_ID
            or not env.get("CODEX_THREAD_ID")
            or review.get("automation_id") != eod_feedback.AUTOMATION_ID
            or review.get("thread_id") != env["CODEX_THREAD_ID"]):
        raise ValueError("EOD_CLOSEOUT_OWNER_MISMATCH")
    evidence = review["evidence"]
    required = {"paper_terminal", "paper_manifest", "app_eod", "statement", "research", "feedback", "daily_review",
                "statement_terminal", "research_terminal", "feedback_terminal", "statement_stdout"}
    if not required <= evidence.keys():
        raise ValueError("EOD_CLOSEOUT_ORIGINAL_EVIDENCE_REQUIRED")
    for ref in evidence.values():
        if eod_feedback.evidence_ref(root, Path(ref["path"])) != ref:
            raise ValueError("EOD_CLOSEOUT_EVIDENCE_MISMATCH")

    def load(role: str) -> dict:
        return json.loads((root / evidence[role]["path"]).read_bytes())

    paper, manifest, app, statement = (load(role) for role in
                                      ("paper_terminal", "paper_manifest", "app_eod", "statement"))
    day, owner = review["date"], review["thread_id"]
    latest_exit = None
    for step, command in COMMANDS.items():
        receipt = load(step + "_terminal")
        started = datetime.fromisoformat(receipt["started_at"])
        ended = datetime.fromisoformat(receipt["finished_at"])
        if (receipt.get("automation_id") != eod_feedback.AUTOMATION_ID
                or receipt.get("thread_id") != owner or receipt.get("date") != day
                or receipt.get("step") != step or receipt.get("command") != command
                or type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0
                or started.utcoffset() is None or ended.utcoffset() is None
                or started.date().isoformat() != day or ended.date().isoformat() != day or ended < started):
            raise ValueError("EOD_CLOSEOUT_POST_COMMAND_NOT_ORIGINAL_TERMINAL")
        ref = receipt["stdout"]
        if eod_feedback.evidence_ref(root, Path(ref["path"])) != ref:
            raise ValueError("EOD_CLOSEOUT_POST_COMMAND_OUTPUT_MISMATCH")
        if step in {"research", "feedback"} and ref != evidence[step]:
            raise ValueError("EOD_CLOSEOUT_POST_COMMAND_OUTPUT_UNBOUND")
        if step == "statement":
            if ref != evidence["statement_stdout"]:
                raise ValueError("EOD_CLOSEOUT_STATEMENT_OUTPUT_UNBOUND")
            output = json.loads((root / ref["path"]).read_bytes())
            if (root / output["report_path"]).resolve() != (root / evidence["statement"]["path"]).resolve():
                raise ValueError("EOD_CLOSEOUT_STATEMENT_OUTPUT_UNBOUND")
        latest_exit = max(latest_exit, ended) if latest_exit else ended
    reviewed = datetime.fromisoformat(review["reviewed_at"])
    if reviewed.utcoffset() is None or reviewed < latest_exit or reviewed.date().isoformat() != day:
        raise ValueError("EOD_CLOSEOUT_REVIEW_PRECEDES_POST_BUSINESS_TERMINALS")
    paper_path = root / evidence["paper_terminal"]["path"]
    manifest_path = root / evidence["paper_manifest"]["path"]
    if (paper_path.parent != manifest_path.parent or paper_path.name != "terminal.json"
            or manifest_path.name != "manifest.json" or paper.get("automation") != "eod"
            or paper.get("market_date") != day or type(paper.get("process_exit_code")) is not int
            or not paper.get("terminal_reason") or paper.get("run_id") != manifest.get("run_id")
            or manifest.get("automation_id") != eod_feedback.AUTOMATION_ID
            or manifest.get("thread_id") != owner or manifest.get("market_date") != day):
        raise ValueError("EOD_CLOSEOUT_PAPER_NOT_TERMINAL_OR_OWNER_MISMATCH")
    identity = app.get("automation_identity", {})
    if (app.get("phase") != "eod" or app.get("trade_date") != day
            or app.get("status") not in {"observed", "blocked", "no_action", "settled"}
            or identity.get("automation_id") != eod_feedback.AUTOMATION_ID
            or identity.get("thread_id") != owner or identity.get("trade_date") != day):
        raise ValueError("EOD_CLOSEOUT_APP_NOT_TERMINAL_OR_OWNER_MISMATCH")
    accounting = (app.get("account") or {}).get("accounting")
    if statement.get("schema_version") != "book-b-statement.v2":
        raise ValueError("EOD_CLOSEOUT_STATEMENT_INVALID")
    if accounting and statement.get("source_observation") != accounting:
        raise ValueError("EOD_CLOSEOUT_STATEMENT_NOT_ORIGINAL_OBSERVATION")
    research = load("research")
    research_status = research.get("status")
    research_observed = research_status == "observed" and research.get("phase") == "eod"
    research_not_started = (research_status == "not_started"
                            and (research.get("reports") or {}).get("status") == "reported")
    if (research.get("authority") != 0
            or not (research_observed or research_not_started or research_status == "NON_TRADING_DAY")):
        raise ValueError("EOD_CLOSEOUT_RESEARCH_NOT_TERMINAL")
    if load("feedback").get("status") != "audited":
        raise ValueError("EOD_CLOSEOUT_FEEDBACK_NOT_TERMINAL")
    digest = build_digest(live_dir=root / "output/live", market_date=day)
    digest.pop("generated_at", None)
    app_digest = digest.get("book_b_app") or {}
    if accounting:
        receipt = accounting.get("receipt_sha256", "")
        if (not re.fullmatch(r"[0-9a-f]{64}", receipt)
                or app_digest.get("valuation_status") != "dated_observation"
                or app_digest.get("receipt_sha256") != receipt):
            raise ValueError("EOD_CLOSEOUT_DIGEST_NOT_ORIGINAL_OBSERVATION")
    else:
        digest["book_b_app"] = {"valuation_status": "unavailable", "reason": app.get("reason", "EOD_ACCOUNT_UNAVAILABLE")}
    # The final dated text is frozen with the reviewed handoff. A later account
    # change cannot silently turn a delivery retry into another dated message.
    path = eod_feedback.record_daily(root, dict(review, digest=digest, research_status=research_status))
    if paper["process_exit_code"] != 0 or paper.get("deterministic_status") != "succeeded":
        delivery = {"delivery": "blocked", "reason": "PAPER_EOD_FAILED"}
    else:
        delivery = push_digest(digest) if push_digest is not None else {"delivery": "not_requested"}
    return {"status": "recorded", "authority": 0, "daily_feedback": str(path),
            "daily_feedback_sha256": eod_feedback.sha(path.read_bytes()), "delivery": delivery,
            "research_status": research_status,
            "paper_status": paper.get("deterministic_status"), "app_status": app.get("reason"),
            "digest": digest}

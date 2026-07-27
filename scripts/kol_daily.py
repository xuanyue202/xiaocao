#!/usr/bin/env python3
"""Run or inspect the short-lived Ticket 07 KOL daytime operation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from xiaocao.kol.daily import (
    build_triggered_evaluation_candidate,
    DailyCoordinator,
    DailyError,
    DailyPublicationContext,
    DailyPublicationPipeline,
    TransientSourceError,
    UserActionBlocker,
    triggered_evaluation_terminal,
)
from xiaocao.kol.decisions import DecisionPipeline
from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.household import LiangHuiMcpClient
from xiaocao.kol.lv_subscription import LvSubscriptionService
from xiaocao.kol.publication import PublicationLedger, read_published_publication
from xiaocao.kol.subscription_video import SubscriptionVideoService
from xiaocao.kol.xiaocao_live import (
    XiaocaoLiveService,
    validate_decision_bundle,
)
from xiaocao.live.notify import notify


DEFAULT_OUTPUT = Path("output/live/kol_daily")
DEFAULT_DECISIONS = Path("output/live/kol_intelligence")
DEFAULT_LV_OUTPUT = Path("output/live/kol_lv_subscription")
DEFAULT_VIDEO_OUTPUT = Path("output/live/kol_subscription_videos")
DEFAULT_XIAOCAO_OUTPUT = Path("output/live/kol_xiaocao_live")
MAX_HANDOFF_BYTES = 1024 * 1024
_RETRYABLE_ITEM_ERRORS = {
    "subscription browser command failed",
    "subscription browser command timed out",
    "subscription browser download outcome is uncertain",
    "subscription browser download waiter did not start",
}


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _read_agent_path(request: dict[str, Any], field: str) -> Path:
    print(json.dumps(request, ensure_ascii=False, sort_keys=True), flush=True)
    response = sys.stdin.readline()
    if not response:
        raise DailyError(f"daily runner requires {field} on stdin")
    raw = response.strip()
    if raw.startswith("{"):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DailyError("daily runner response is invalid JSON") from exc
        raw = str(value.get(field) or "").strip()
    if not raw:
        raise DailyError(f"daily runner response lacks {field}")
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise DailyError(f"daily runner {field} is missing")
    return path


def _sender(title: str, body: str) -> dict[str, str]:
    result = notify(title, body, macos=False, audience="kol")
    if not isinstance(result, dict):
        raise DailyError("KOL notification relay returned an invalid result")
    return {str(key): str(value) for key, value in result.items()}


def _classified_source(name: str, runner):
    def run():
        try:
            return runner()
        except DailyError:
            raise
        except EnrichmentError as exc:
            message = str(exc)
            if message == "Lv subscription share URL is invalid":
                raise UserActionBlocker(
                    "lv-share-url-invalid",
                    "请更新 xiaocao.yaml 中吕晓彤唯一百度分享链接。",
                ) from exc
            if message == "Lv subscription share code is missing":
                raise UserActionBlocker(
                    "lv-share-code-missing",
                    "请补全 xiaocao.yaml 中吕晓彤唯一百度分享提取码。",
                ) from exc
            if message == "Lv subscription share is expired":
                raise UserActionBlocker(
                    "lv-share-expired",
                    "请更新 xiaocao.yaml 中吕晓彤唯一百度分享链接和提取码；当前分享页已失效。",
                ) from exc
            if message in {
                "OpenCLI session is not authenticated",
                "OpenCLI login is required",
            }:
                raise UserActionBlocker(
                    f"{name}-opencli-login",
                    "请在已授权浏览器中重新登录百度网盘，并保持既有 OpenCLI 会话可访问。",
                ) from exc
            if message == "captcha_required":
                raise UserActionBlocker(
                    f"{name}-captcha",
                    "请在已授权百度网盘页面完成验证码，然后等待下一小时自动恢复。",
                ) from exc
            raise TransientSourceError(message) from exc

    return run


class DailyRuntime:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.client = (
            LiangHuiMcpClient.from_config(args.lianghui_config)
            if args.lianghui_config is not None
            else LiangHuiMcpClient.from_config()
        )
        self.publications = PublicationLedger(args.output_dir / "publications")

    def _pipeline(
        self,
        context: DailyPublicationContext,
    ) -> DailyPublicationPipeline:
        delegate = DecisionPipeline(
            self.args.decision_output_dir,
            household_context_loader=self.client.load_context,
        )
        return DailyPublicationPipeline(
            delegate,
            ledger=self.publications,
            client=self.client,
            context=context,
        )

    @staticmethod
    def _terminal(result_path: Path | str) -> dict[str, Any]:
        value = json.loads(Path(result_path).read_text(encoding="utf-8"))
        try:
            terminal = value["items"][0]["daily_terminal"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DailyError("source result lacks a Ticket 07 terminal") from exc
        if not isinstance(terminal, dict):
            raise DailyError("source Ticket 07 terminal is invalid")
        return terminal

    def lv(self) -> dict[str, Any]:
        service = LvSubscriptionService.from_config(
            self.args.lv_output_dir,
            config_path=self.args.config,
        )
        service.poll_opencli(
            session=self.args.lv_session,
            profile=self.args.opencli_profile,
        )
        pending = service.pending_items()
        if not pending:
            return {"status": "no_update"}
        events = []
        waiting = 0
        for row in pending:
            identity = str(row["identity"])
            try:
                service.download_opencli(
                    identity,
                    session=self.args.lv_session,
                    profile=self.args.opencli_profile,
                )
            except EnrichmentError as exc:
                if str(exc) not in _RETRYABLE_ITEM_ERRORS:
                    raise
                waiting += 1
                continue
            ingest = service.ingest_browser_download(identity)
            request = service.prepare_analysis_request(ingest)
            bundle_path = _read_agent_path(
                {
                    "event": "daily_analysis_input_required",
                    "adapter": "lv_text_image",
                    "identity": ingest["identity"],
                    "version_key": ingest["version_key"],
                    "analysis_request_path": request["request_path"],
                    "evidence_path": ingest["evidence_path"],
                    "required_content_value": (
                        "low_density|promoted(report_only|alert_eligible)"
                    ),
                },
                "bundle_path",
            )
            context = DailyPublicationContext(
                adapter="lv_text_image",
                source_identity=str(ingest["identity"]),
                publication_version=str(ingest["version_key"]),
                kol_id="kol-lv-xiaotong",
                source="吕晓彤订阅",
                source_published_at=str(ingest["published_at"]),
                media_types=(str(ingest["media_type"]),),
                source_parts=({
                    "identity": str(ingest["identity"]),
                    "version": str(ingest["version_key"]),
                    "order": 1,
                    "size": 0,
                    "evidence_sha256": str(ingest["evidence_sha256"]),
                },),
            )
            state = service.decide(
                identity,
                bundle_path=bundle_path,
                decision_output_dir=self.args.decision_output_dir,
                sender=_sender,
                pipeline=self._pipeline(context),
            )
            events.append(self._terminal(state["decision_result_path"]))
        if events:
            return {
                "status": "completed",
                "events": events,
                "waiting_count": waiting,
            }
        return {"status": "waiting", "waiting_count": waiting}

    def videos(self) -> dict[str, Any]:
        service = SubscriptionVideoService(
            self.args.video_output_dir,
            config_path=self.args.config,
        )
        service.scan_opencli(
            lv_session=self.args.lv_session,
            private_session=self.args.private_session,
            profile=self.args.opencli_profile,
        )
        pending = service.pending_items()
        if not pending:
            return {"status": "no_update"}
        events = []
        waiting = 0
        for item in pending:
            state = service.advance_item(
                item,
                lv_session=self.args.lv_session,
                private_session=self.args.private_session,
                enrichment_session=self.args.enrichment_session,
                profile=self.args.opencli_profile,
            )
            if state.get("event") != "subscription_video_analysis_input_required":
                waiting += 1
                continue
            bundle_path = _read_agent_path(
                {
                    **state,
                    "adapter": "subscription_video",
                    "required_content_value": (
                        "low_density|promoted(report_only|alert_eligible)"
                    ),
                },
                "bundle_path",
            )
            parts = item.get("parts") or [item]
            context = DailyPublicationContext(
                adapter="subscription_video",
                source_identity=str(item["identity"]),
                publication_version=str(item["version_key"]),
                kol_id=(
                    "kol-lucifer"
                    if item["author"] == "路西法"
                    else "kol-lv-xiaotong"
                ),
                source=str(item["source"]),
                source_published_at=str(
                    item.get("published_at")
                    or item.get("modified_at")
                    or state.get("updated_at")
                ),
                media_types=("video",),
                source_parts=tuple(
                    {
                        "identity": str(part["identity"]),
                        "version": str(part["version_key"]),
                        "order": index,
                        "size": int(part.get("size") or 0),
                        "evidence_sha256": str(
                            state.get("transcript_sha256")
                            or state.get("episode_evidence_sha256")
                        ),
                    }
                    for index, part in enumerate(parts, start=1)
                ),
            )
            decision = service.decide_item(
                item,
                bundle_path=bundle_path,
                decision_output_dir=self.args.decision_output_dir,
                sender=_sender,
                pipeline=self._pipeline(context),
            )
            events.append(self._terminal(decision["decision_result_path"]))
        if events:
            return {"status": "completed", "events": events}
        return {"status": "waiting", "waiting_count": waiting}

    @staticmethod
    def _handoff(path: Path) -> dict[str, Any]:
        if path.stat().st_size > MAX_HANDOFF_BYTES:
            raise DailyError("Xiaocao handoff exceeds the lightweight boundary")
        value = json.loads(path.read_text(encoding="utf-8"))
        expected = str(value.get("handoff_sha256") or "")
        unsigned = dict(value)
        unsigned.pop("handoff_sha256", None)
        actual = hashlib.sha256(_canonical(unsigned).encode()).hexdigest()
        if (
            expected != actual
            or value.get("large_payload_local_bytes") != 0
            or "media_path" in value
            or "video_path" in value
        ):
            raise DailyError("Xiaocao lightweight handoff is invalid")
        return value

    def xiaocao(self) -> dict[str, Any]:
        service = XiaocaoLiveService(
            self.args.xiaocao_output_dir,
            decision_output=self.args.decision_output_dir,
        )
        handoffs = sorted(
            (self.args.xiaocao_output_dir / "handoffs").glob("*.json")
        )
        events = []
        waiting = 0
        for path in handoffs:
            handoff = self._handoff(path)
            job_id = str(handoff["netdisk_job_id"])
            state = service.netdisk.status(job_id)
            if state.get("status") == "decided":
                result_path = Path(str(state.get("decision_result_path") or ""))
                if result_path.is_file():
                    value = json.loads(result_path.read_text(encoding="utf-8"))
                    if (value.get("items") or [{}])[0].get("daily_terminal"):
                        continue
                # Historical completed work is never replayed.
                continue
            if state.get("status") not in {"transcript_captured", "verified"}:
                state = service.netdisk.advance_opencli(
                    job_id,
                    session=self.args.enrichment_session,
                    profile=self.args.opencli_profile,
                )
            if state.get("status") == "transcript_captured":
                audit_path = _read_agent_path(
                    {
                        "event": "daily_xiaocao_audit_input_required",
                        "capture_job_id": handoff["capture_job_id"],
                        "transcript_path": state["transcript_path"],
                        "transcript_sha256": state["transcript_sha256"],
                    },
                    "audit_path",
                )
                state = service.netdisk.verify_transcript(
                    job_id,
                    audit_path=audit_path,
                )
            if state.get("status") != "verified":
                waiting += 1
                continue
            bundle_path = _read_agent_path(
                {
                    "event": "daily_analysis_input_required",
                    "adapter": "xiaocao_live",
                    "capture_job_id": handoff["capture_job_id"],
                    "transcript_path": state["transcript_path"],
                    "transcript_sha256": state["transcript_sha256"],
                    "required_content_value": (
                        "low_density|promoted(report_only|alert_eligible)"
                    ),
                },
                "bundle_path",
            )
            validate_decision_bundle(
                bundle_path,
                transcript_path=Path(state["transcript_path"]),
                transcript_sha256=str(state["transcript_sha256"]),
            )
            context = DailyPublicationContext(
                adapter="xiaocao_live",
                source_identity=str(handoff["capture_job_id"]),
                publication_version=str(state["transcript_sha256"]),
                kol_id="kol-xiaocao",
                source="小草直播",
                source_published_at=str(handoff["published_at"]),
                media_types=("video",),
                source_parts=({
                    "identity": str(handoff["capture_job_id"]),
                    "version": str(state["transcript_sha256"]),
                    "order": 1,
                    "size": 0,
                    "evidence_sha256": str(state["transcript_sha256"]),
                },),
            )
            decided = service.netdisk.decide(
                job_id,
                bundle_path=bundle_path,
                decision_output_dir=self.args.decision_output_dir,
                sender=_sender,
                pipeline=self._pipeline(context),
            )
            events.append(self._terminal(decided["decision_result_path"]))
        if events:
            return {"status": "completed", "events": events}
        if waiting:
            return {"status": "waiting", "waiting_count": waiting}
        return {"status": "no_update"}

    def viewpoints(self) -> dict[str, Any]:
        trigger_dir = self.args.output_dir / "viewpoint_triggers"
        receipt_dir = self.args.output_dir / "viewpoint_receipts"
        if not trigger_dir.is_dir():
            return {"status": "no_update"}
        terminals = []
        for path in sorted(trigger_dir.glob("*.json")):
            if path.stat().st_size > MAX_HANDOFF_BYTES:
                raise DailyError("viewpoint trigger exceeds the small-payload boundary")
            trigger_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            receipt_path = receipt_dir / f"{trigger_sha}.json"
            if receipt_path.is_file():
                try:
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    terminal = receipt["terminal"]
                except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise DailyError(
                        "viewpoint maintenance receipt is invalid"
                    ) from exc
                terminals.append(terminal)
                continue
            request = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(request, dict):
                raise DailyError("viewpoint trigger must be a JSON object")
            current = read_published_publication(
                self.client,
                str(request.get("report_id") or ""),
            )
            candidate = build_triggered_evaluation_candidate(current, request)
            self.publications.prepare(
                candidate["publication_key"],
                candidate["records"],
                candidate["publish_request"],
                metadata=candidate["metadata"],
            )
            state = self.publications.run(
                candidate["publication_key"],
                self.client,
            )
            terminal = triggered_evaluation_terminal(candidate, state)
            terminals.append(terminal)
            receipt_dir.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "trigger_sha256": trigger_sha,
                        "terminal": terminal,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        return (
            {"status": "completed", "events": terminals}
            if terminals
            else {"status": "no_update"}
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "audit"))
    parser.add_argument("--config", type=Path, default=Path("xiaocao.yaml"))
    parser.add_argument("--lianghui-config", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--decision-output-dir", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--lv-output-dir", type=Path, default=DEFAULT_LV_OUTPUT)
    parser.add_argument("--video-output-dir", type=Path, default=DEFAULT_VIDEO_OUTPUT)
    parser.add_argument(
        "--xiaocao-output-dir", type=Path, default=DEFAULT_XIAOCAO_OUTPUT
    )
    parser.add_argument("--opencli-profile")
    parser.add_argument("--lv-session", default="xiaocao-lv-subscription")
    parser.add_argument("--private-session", default="xiaocao-lv-subscription")
    parser.add_argument("--enrichment-session", default="xiaocao-lv-subscription")
    args = parser.parse_args()
    service = DailyCoordinator(args.output_dir)
    if args.command == "status":
        _print(service.status())
        return 0
    if args.command == "audit":
        _print(service.audit())
        return 0
    runtime = DailyRuntime(args)
    result = service.run(
        [
            {
                "name": "lv_text_image",
                "priority": 10,
                "run": _classified_source("lv_text_image", runtime.lv),
            },
            {
                "name": "subscription_video",
                "priority": 20,
                "run": _classified_source(
                    "subscription_video", runtime.videos
                ),
            },
            {
                "name": "xiaocao_handoff",
                "priority": 30,
                "run": _classified_source(
                    "xiaocao_handoff", runtime.xiaocao
                ),
            },
            {
                "name": "viewpoint_maintenance",
                "priority": 40,
                "run": _classified_source(
                    "viewpoint_maintenance", runtime.viewpoints
                ),
            },
        ],
        blocker_sender=_sender,
    )
    if not result.get("silent"):
        _print(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DailyError, EnrichmentError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc

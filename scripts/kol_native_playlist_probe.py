#!/usr/bin/env python3
"""Probe only an exact native merchant's public recording through its singleton."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.kol.xiaocao_wechat import XiaocaoLiveCaptureDriver, _native_v2_merchant_lineage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--source-identity", required=True)
    parser.add_argument("--network-service", required=True)
    args = parser.parse_args()
    service = XiaocaoLiveCaptureDriver(Path("output/live/kol_xiaocao_live/wechat_subscription"))._service(args.identity)
    capture = service.capture_store.latest(args.capture_id)
    if not capture or capture.get("status") != "awaiting_capture" or capture.get("download_task_id"):
        raise ValueError("manifest probe requires the original awaiting capture")
    service.sniffer.status()
    pac = subprocess.check_output(["/usr/sbin/networksetup", "-getautoproxyurl", args.network_service], text=True)
    if "URL: http://127.0.0.1:2023/proxy.pac" not in pac or "Enabled: Yes" not in pac:
        raise ValueError("manifest probe requires the owned healthy capture PAC")
    prefix, app, live = args.source_identity.split(":")
    if prefix != "xiaoetong":
        raise ValueError("invalid native source")
    candidates = [c for c in service.sniffer.candidates() if c.get("id") == args.candidate_id]
    if not candidates or any(c.get("live_id") != live for c in candidates):
        raise ValueError("manifest probe candidate identity mismatch")
    candidate = max(candidates, key=lambda c: str(c.get("captured") or ""))
    captured = datetime.fromisoformat(candidate["captured"])
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    armed = datetime.fromisoformat(capture.get("native_repair_armed_at") or capture["created_at"])
    if captured <= armed:
        raise ValueError("manifest probe requires a fresh native observation")
    lineage = _native_v2_merchant_lineage(candidate, app_id=app, live_id=live,
        armed_at=armed, captured_at=captured, debug_root=service.sniffer_binary.parent / "elive_live_debug", public_probe=True)
    print(json.dumps({"capture_id": args.capture_id, "candidate_id": args.candidate_id,
        "source_identity": args.source_identity, "lineage": lineage}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

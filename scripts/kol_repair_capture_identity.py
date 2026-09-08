#!/usr/bin/env python3
"""Correct a pre-download identity in place; default is a read-only plan."""
import argparse
import fcntl
import hashlib
import json
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.kol.capture_identity_repair import corrected_rows
from xiaocao.kol.xiaocao_wechat import XiaocaoLiveCaptureDriver, _atomic_json, _append_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path("output/live/kol_xiaocao_live/wechat_subscription").resolve()
    if Path(args.identity).name != args.identity:
        raise ValueError("invalid identity")
    service = XiaocaoLiveCaptureDriver(root)._service(args.identity)
    evidence = json.loads(args.evidence.read_text())
    manifest_path = root / "manifest.json"
    with Path("output/live/kol_daily/.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads(manifest_path.read_text())
        item = manifest["items"][args.identity]
        capture = service.capture_store.latest(item["capture_job_id"])
        source_path = service.sniffer_binary.parent / "elive_source_jobs/jobs.jsonl"
        source_bytes = source_path.read_bytes()
        jobs = [json.loads(line) for line in source_bytes.splitlines() if line.strip()]
        job = [row for row in jobs if row["id"] == capture["source_job_id"]][-1]
        live = evidence["source_identity"].rsplit(":", 1)[-1]
        candidates = service.sniffer.candidates()
        candidate = next(row for row in candidates if row["id"] == evidence["candidate_id"])
        tasks = service.sniffer.tasks()
        for task in tasks:
            if task.get("status") in {"running", "ready", "wait"}:
                raise ValueError("active download blocks source manager restart")
            meta = task.get("meta") or {}
            labels = meta.get("labels") or (meta.get("req") or {}).get("labels") or {}
            if labels.get("live_id") in {job["live_id"], live} or labels.get("source_job_id") == job["id"]:
                raise ValueError("an existing task blocks pre-download correction")
        remote = service.sniffer.xiaoetong_source_job(job["id"])
        if remote.get("status") != job["status"] or remote.get("live_id") != job["live_id"] or remote.get("task_id"):
            raise ValueError("source manager disagrees with disk")
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
        updated_item, updated_capture, updated_job = corrected_rows(
            item, capture, job, evidence["page_url"], candidate, evidence, now)
        proof = {"status": "planned", "identity": args.identity,
                 "capture_job_id": capture["job_id"], "source_job_id": job["id"],
                 "correction": updated_job["identity_correction"]}
        if not args.apply:
            print(json.dumps(proof, ensure_ascii=False)); return
        backup = service.output_dir / "receipts" / "identity-repair-before.json"
        if backup.exists():
            raise ValueError("repair already claimed; reconcile its receipt before continuing")
        _atomic_json(backup, {"item": item, "capture": capture, "source_job": job,
                             "source_ledger_sha256": hashlib.sha256(source_bytes).hexdigest(),
                             "evidence": evidence, "plan": proof})
        pids = service._sniffer_pids()
        if len(pids) != 1:
            raise ValueError("expected one sniffer")
        service._disable_owned_capture_pac()
        os.kill(pids[0], signal.SIGINT)
        for _ in range(100):
            if not service._sniffer_pids():
                break
            time.sleep(0.1)
        snapshot = service.cleanup_snapshot()
        if not snapshot["process_gone"] or any(snapshot["listeners"].values()):
            raise ValueError("source manager did not stop")
        if source_path.read_bytes() != source_bytes:
            raise ValueError("source ledger changed before correction")
        _append_jsonl(source_path, updated_job)
        service.capture_store._append(updated_capture)
        manifest["items"][args.identity] = updated_item
        manifest["updated_at"] = now
        _atomic_json(manifest_path, manifest)
        service._append("source_identity_corrected", **proof["correction"],
                        capture_job_id=capture["job_id"], source_job_id=job["id"],
                        playback_window_closed=True, media_request_observed=True)
        # Existing capture ID and baseline are reused. No arm or UI operation.
        ready = service.start()
        if ready["capture_job_id"] != capture["job_id"]:
            raise ValueError("resumed another capture")
        readback = service.sniffer.xiaoetong_source_job(job["id"])
        if readback["live_id"] != live:
            raise ValueError("corrected source did not reload")
        proof.update(status="corrected", source_readback=readback)
        _atomic_json(service.output_dir / "receipts/identity-repair-after.json", proof)
        print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()

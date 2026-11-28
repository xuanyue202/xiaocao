"""Read-only timing observations beside funded Book B research, with separate receipts."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.api.client import XiaocaoClient
from xiaocao.live.morning_bundle import inspect_bundle
from xiaocao.utils.atomic_files import atomic_write

CHINA = ZoneInfo("Asia/Shanghai")
GROUPS = ("jieli", "dixi", "qibao")
MORNING = ("0927", "0932", "0947")
CLOSE = "1517"


def opening_members(live, day):
    proof = inspect_bundle(live, day)
    if proof["status"] != "ready":
        raise ValueError("original_freeze_unavailable")
    ptr = json.loads((live / f"morning_bundle_commit_{day}.json").read_bytes())
    raw = Path(ptr["checkpoint_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != proof["checkpoint_sha256"]:
        raise ValueError("original_checkpoint_changed")
    pools = {}
    for s in json.loads(raw)["capture"]["source_readiness"]["sources"]:
        group = s["source"].removeprefix("pool:")
        if s["source"] == group or group not in GROUPS:
            continue
        if s.get("requested_date") != day or group in pools:
            raise ValueError("original_pool_identity_mismatch")
        payload = Path(s["response_path"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != s["response_sha256"]:
            raise ValueError("original_pool_changed")
        pools[group] = {
            "codes": json.loads(payload),
            "observed_at": s["observed_at"],
            "response_sha256": s["response_sha256"],
        }
    if set(pools) != set(GROUPS):
        raise ValueError("original_pool_missing")
    return {"checkpoint_sha256": proof["checkpoint_sha256"], "pools": pools}


def fetch_pools(client, day, deadline, clock):
    records = {}
    for group in GROUPS:
        start = clock()
        entry = {"requested_day": day, "group": group, "started_at": start.isoformat()}
        records[group] = entry
        if start >= deadline:
            entry["status"] = "window_missed"
            continue
        try:
            codes = client.get_code_list_v2(day, group, 0, 0)
            end = clock()
            entry["completed_at"] = end.isoformat()
            if end >= deadline:
                entry["status"] = "late_response"
            elif not codes:
                entry["status"] = "empty_unconfirmed"
            elif not all(
                isinstance(c, str) and re.fullmatch(r"\d{6}\.(XSHG|XSHE|BJSE)", c)
                for c in codes
            ):
                entry["status"] = "unexpected_identity"
            else:
                entry.update(status="observed", codes=codes)
        except Exception as exc:
            entry.update(
                status="read_error",
                reason=type(exc).__name__,
                completed_at=clock().isoformat(),
            )
    return records


def observe_relay_ranking(client, day, pool, deadline, clock):
    """Sample the supplier's relay order and the two scores for that same membership."""
    record = {"sort_id": 37, "requested_day": day, "reads": [], "stocks": []}
    if pool["status"] != "observed":
        return {**record, "status": "pool_unavailable"}
    codes = pool["codes"]
    members = set(codes)
    if len(members) != len(codes):
        return {**record, "status": "duplicate_pool_member"}

    def read(kind, fetch):
        start = clock()
        if start >= deadline:
            raise TimeoutError("window_missed")
        stamp = {"kind": kind, "started_at": start.isoformat()}
        record["reads"].append(stamp)
        try:
            rows = fetch()
        finally:
            end = clock()
            stamp["completed_at"] = end.isoformat()
        if end >= deadline:
            raise TimeoutError("late_response")
        return rows

    try:
        ranking = read("sort:37", lambda: client.sort_v2(codes, 37, date=day))
        # The provider can return the whole market. Keep its relative order within the pool.
        if not isinstance(ranking, list):
            return {**record, "status": "invalid_ranking"}
        ordered = [c for c in ranking if c in members]
        if len(ordered) != len(codes) or set(ordered) != members:
            return {**record, "status": "incomplete_ranking"}
        record["ordered_codes"] = ordered
        incomplete = False
        for offset in range(0, len(ordered), 80):
            batch = ordered[offset : offset + 80]
            rows = read("stock_index", lambda: client.get_xiao_cao_index_v2(day, batch))
            by_code = {row["code"]: row for row in rows}
            if len(rows) != len(batch) or set(by_code) != set(batch):
                return {**record, "status": "score_identity_mismatch"}
            for code in batch:
                stock = {"code": code}
                for field in ("jsjl", "xcjw"):
                    value = by_code[code].get(field)
                    valid = type(value) in (int, float) and math.isfinite(value)
                    stock[field] = value if valid else None
                    incomplete |= not valid
                record["stocks"].append(stock)
        record["status"] = "missing_scores" if incomplete else "observed"
    except TimeoutError as exc:
        reason = str(exc)
        record["status"] = (
            reason if reason in {"window_missed", "late_response"} else "read_error"
        )
    except Exception as exc:
        record.update(status="read_error", reason=type(exc).__name__)
    return record


def membership_match(a, b):
    if not a or not b:
        return None
    left, right = set(a), set(b)
    return {
        "observed": len(left),
        "reference": len(right),
        "common": len(left & right),
        "equal": left == right,
    }


def encoded(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def read_receipt(path, day, slot, previous):
    if not path.is_file():
        return None, "missing_receipt"
    try:
        record = json.loads(path.read_bytes())
        if record.pop("receipt_sha256") != hashlib.sha256(encoded(record)).hexdigest():
            return None, "receipt_hash_mismatch"
        if record["day"] != day or record["slot"] != slot:
            return None, "receipt_identity_mismatch"
        fields = {"current": day}
        if slot == CLOSE:
            fields["prior_date_read"] = previous
        for key, date in fields.items():
            groups = record[key]
            if set(groups) != set(GROUPS) or any(
                row["requested_day"] != date or row["group"] != name
                for name, row in groups.items()
            ):
                return None, "receipt_group_or_date_mismatch"
        return record, None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None, "invalid_receipt"


def observe_session(
    root,
    live,
    day,
    previous,
    early,
    base_url,
    *,
    clock=None,
    sleep=time.sleep,
    client=None,
):
    clock = clock or (lambda: datetime.now(CHINA))
    client = client or XiaocaoClient(
        base_url=base_url,
        timeout=3,
        retries=0,
        cache=None,
        minimum_request_interval=0.9,
    )
    directory = root / day
    summary = {}
    for minute in MORNING if early else (CLOSE,):
        path = directory / f"{minute}.json"
        target = datetime.fromisoformat(f"{day}T{minute[:2]}:{minute[2:]}:00").replace(
            tzinfo=CHINA
        )
        deadline = target + timedelta(minutes=15 if minute == CLOSE else 1)
        if not path.exists():
            while (remaining := (target - clock()).total_seconds()) > 0:
                sleep(min(remaining, 15))
            current = fetch_pools(client, day, deadline, clock)
            receipt = {"day": day, "slot": minute, "current": current, "authority": 0}
            try:
                receipt["opening"] = opening_members(live, day)
            except (KeyError, ValueError, OSError, TypeError) as exc:
                receipt["opening_error"] = str(exc)
            if minute == CLOSE:
                prior = fetch_pools(client, previous, deadline, clock)
                receipt["prior_date_read"] = prior
                comparisons = {}
                morning_records = {}
                receipt["morning_receipt_errors"] = {}
                for m in MORNING:
                    record, error = read_receipt(
                        directory / f"{m}.json", day, m, previous
                    )
                    if error:
                        receipt["morning_receipt_errors"][m] = error
                    else:
                        morning_records[m] = record
                for g in GROUPS:
                    samples = {
                        "opening": receipt.get("opening", {})
                        .get("pools", {})
                        .get(g, {})
                        .get("codes")
                    }
                    samples.update(
                        {
                            m: morning_records[m]["current"][g].get("codes")
                            if m in morning_records
                            else None
                            for m in MORNING
                        }
                    )
                    comparisons[g] = {
                        m: {
                            "prior_date": membership_match(
                                codes, prior[g].get("codes")
                            ),
                            "same_date_afternoon": membership_match(
                                codes, current[g].get("codes")
                            ),
                        }
                        for m, codes in samples.items()
                    }
                receipt["comparisons"] = comparisons
            receipt["relay_ranking"] = observe_relay_ranking(
                client, day, current["jieli"], deadline, clock
            )
            receipt["receipt_sha256"] = hashlib.sha256(encoded(receipt)).hexdigest()
            atomic_write(path, encoded(receipt) + b"\n", immutable=True)
        data, error = read_receipt(path, day, minute, previous)
        if error:
            summary[minute] = {"path": str(path), "complete": False, "error": error}
            continue
        observations = list(data["current"].values()) + list(
            data.get("prior_date_read", {}).values()
        )
        complete = not data.get("opening_error") and all(
            x["status"] == "observed" for x in observations
        )
        if minute == CLOSE:
            complete = complete and all(
                row["same_date_afternoon"] is not None
                for stages in data["comparisons"].values()
                for row in stages.values()
            )
        summary[minute] = {
            "path": str(path),
            "complete": complete,
            "relay_rank_status": data.get("relay_ranking", {}).get(
                "status", "legacy_unobserved"
            ),
        }
    return summary

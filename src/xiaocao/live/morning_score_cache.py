"""Prior-day score preparation, with no network/model work at consumption."""
from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
from datetime import date
from pathlib import Path

from .morning_bundle import acquire_bundle, read_consumed_rows


def model_fingerprint(root: Path) -> str:
    files = [root / "kronos_screen/model" / name for name in ("K_kronos.joblib", "P_priorday.joblib")]
    files += [root / "kronos_screen/scripts" / name for name in (
        "secondary_screen.py", "kronos_lib.py", "build_priorday_feats.py")]
    from huggingface_hub.constants import HF_HUB_CACHE
    hub = Path(HF_HUB_CACHE)
    for name in ("Kronos-base", "Kronos-Tokenizer-base"):
        folder = hub / ("models--NeoQuasar--" + name)
        ref = folder / "refs/main"
        if not ref.is_file():
            raise ValueError("MORNING_SCORE_LOCAL_MODEL_REQUIRED")
        revision = ref.read_text().strip()
        files.append(ref)
        weights = [p for p in (folder / "snapshots" / revision).rglob("*")
                   if p.suffix in {".json", ".bin", ".safetensors"}]
        if not weights:
            raise ValueError("MORNING_SCORE_LOCAL_WEIGHTS_REQUIRED")
        files.extend(weights)
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)]
    return hashlib.sha256(json.dumps(hashes).encode()).hexdigest()


def previous_codes(live_dir: Path, day: str) -> list[str]:
    for folder in sorted((live_dir / "morning_bundles").glob("*"), reverse=True):
        try:
            date.fromisoformat(folder.name)
        except ValueError:
            continue
        if folder.name >= day:
            continue
        result = acquire_bundle(live_dir, folder.name, repair=False)
        if result.get("status") != "ready":
            continue
        return sorted({str(r["code"]) for r in read_consumed_rows(result, folder.name, live_dir=live_dir)})
    return []


def cache_path(root: Path, day: str) -> Path:
    return root / "output/live/morning_scores" / (day + ".json")


def load_scores(root: Path, day: str) -> dict:
    try:
        path = cache_path(root, day)
        if path.is_symlink():
            return {}
        record = json.loads(path.read_text())
        body = {k:v for k,v in record.items() if k != "sha256"}
        date.fromisoformat(record["trade_date"])
        date.fromisoformat(record["input_max_date"])
        if not isinstance(record.get("scores"), dict) or not record.get("input_hashes"):
            return {}
        if (record["trade_date"] != day or record["model_fingerprint"] != model_fingerprint(root)
                or record["input_max_date"] >= day
                or hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest() != record["sha256"]):
            return {}
        archive = path.parent / day / (record["sha256"] + ".json")
        if archive.is_symlink() or json.loads(archive.read_text()) != record:
            return {}
        return {**record, "archive_path": str(archive)}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def save_scores(root: Path, day: str, scores: dict, *, fingerprint: str,
                input_max_date: str, input_hashes: list[str], completed_at: str) -> dict:
    date.fromisoformat(day)
    date.fromisoformat(input_max_date)
    if not input_hashes or input_max_date >= day or model_fingerprint(root) != fingerprint:
        raise ValueError("MORNING_SCORE_INPUT_OR_MODEL_CHANGED")
    body = {"schema_version": 1, "trade_date": day, "model_fingerprint": fingerprint,
        "input_max_date": input_max_date, "input_hashes": input_hashes,
        "scores": scores, "completed_at": completed_at}
    body["sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest()
    path = cache_path(root, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    archive = path.parent / day / (body["sha256"] + ".json")
    archive.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(body, sort_keys=True, allow_nan=False)
    try:
        with archive.open("x") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if archive.read_text() != encoded:
            raise ValueError("MORNING_SCORE_IMMUTABLE_CONFLICT")
    temporary = path.with_suffix(".tmp-" + str(os.getpid()))
    temporary.write_text(encoded)
    os.replace(temporary, path)
    return {**body, "archive_path": str(archive)}


def apply_scores(candidates: list[dict], record: dict, *, top_n: int) -> dict:
    scores = record.get("scores", {})
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)
    for row in candidates:
        saved = scores.get(row["code"], {})
        for key in ("k_score", "p_score"):
            row[key] = saved.get(key) if finite(saved.get(key)) else None
        row["kp_score_basis"] = "prepared_prior_day" if all(finite(row[k]) for k in ("k_score", "p_score")) else "unavailable_neutral"
    valid = [r["k_score"] for r in candidates if finite(r["k_score"])]
    median = statistics.median(valid) if valid else None
    for row in candidates:
        row["kp_keep"] = (finite(row["k_score"]) and row["k_score"] >= median) if median is not None else True
        row.update(kp_rank=9999, kp_star=False)
    survivors = [r for r in candidates if r["kp_keep"]]
    survivors.sort(key=lambda r: -(r["p_score"] if finite(r["p_score"]) else -1e9))
    for rank, row in enumerate(survivors, 1):
        row.update(kp_rank=rank, kp_star=rank <= top_n)
    candidates.sort(key=lambda r: (0 if r["kp_star"] else 1 if r["kp_keep"] else 2, r["kp_rank"]))
    covered = sum(r["kp_score_basis"] == "prepared_prior_day" for r in candidates)
    return {"status": "complete" if covered == len(candidates) else "degraded",
        "covered": covered, "missing": len(candidates)-covered, "cache_sha256": record.get("sha256"),
        "cache_path": record.get("archive_path")}

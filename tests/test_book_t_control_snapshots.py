from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.book_t_shadow import _verify_control_receipts
from xiaocao.research.book_t_shadow import BOOK_T_CONTROL_ARTIFACT_PATHS, BookTShadowError


def _control(root: Path, *, snapshots: bool = True) -> dict:
    day = "2026-11-10"
    receipt = {"artifact_hashes": {}, "artifact_snapshots": {}}
    for name, relative in BOOK_T_CONTROL_ARTIFACT_PATHS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = b'{"book":"T"}\n'
        path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        receipt["artifact_hashes"][name] = digest
        frozen = root / "output/live/book_t_v1_control_artifacts" / day / (digest + path.suffix)
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_bytes(raw)
        receipt["artifact_snapshots"][name] = str(frozen.relative_to(root))
    if not snapshots:
        receipt.pop("artifact_snapshots")
    emitted = root / f"output/live/book_t_v1_control_receipt_{day}.json"
    emitted.write_text(json.dumps(receipt))
    return {"as_of": day, "control": {"control_receipt": receipt}}


def _publish_receipt(root: Path, day: dict) -> None:
    (root / f"output/live/book_t_v1_control_receipt_{day['as_of']}.json").write_text(
        json.dumps(day["control"]["control_receipt"])
    )


def test_shadow_consumes_frozen_control_after_other_books_write(tmp_path: Path) -> None:
    day = _control(tmp_path)
    for name in ("positions", "trades"):
        path = tmp_path / BOOK_T_CONTROL_ARTIFACT_PATHS[name]
        path.write_bytes(path.read_bytes() + b'{"book":"B"}\n')
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    _verify_control_receipts([day], root=tmp_path)

    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_shadow_consumes_control_through_supervisor_shared_output(tmp_path: Path) -> None:
    shared = tmp_path / 'shared'
    shared.mkdir()
    day = _control(shared)
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'output').symlink_to(shared / 'output', target_is_directory=True)
    (shared / BOOK_T_CONTROL_ARTIFACT_PATHS['positions']).write_bytes(b'{"book":"B"}\n')
    _verify_control_receipts([day], root=runtime)


@pytest.mark.parametrize("fault", ["corrupt", "missing", "partial", "null", "outside", "symlink", "wrong_date", "archive_symlink"])
def test_shadow_rejects_bad_snapshot_without_current_file_fallback(tmp_path: Path, fault: str) -> None:
    day = _control(tmp_path)
    receipt = day["control"]["control_receipt"]
    frozen = tmp_path / receipt["artifact_snapshots"]["positions"]
    if fault == "archive_symlink":
        archive = frozen.parent
        other_date = archive.with_name("2026-11-09")
        archive.rename(other_date)
        archive.symlink_to(other_date, target_is_directory=True)
    elif fault == "null":
        receipt["artifact_snapshots"] = None
        _publish_receipt(tmp_path, day)
    elif fault == "corrupt":
        frozen.write_bytes(b"corrupt")
    elif fault == "missing":
        frozen.unlink()
    elif fault == "partial":
        receipt["artifact_snapshots"].pop("positions")
    else:
        target = tmp_path / ("output/live/book_t_v1_control_artifacts/2026-11-09/old.jsonl"
                             if fault == "wrong_date" else "outside.jsonl")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(frozen.read_bytes())
        if fault == "symlink":
            frozen.unlink()
            frozen.symlink_to(target)
        else:
            receipt["artifact_snapshots"]["positions"] = str(target.relative_to(tmp_path))
        _publish_receipt(tmp_path, day)
    if fault == "partial":
        _publish_receipt(tmp_path, day)

    with pytest.raises(BookTShadowError):
        _verify_control_receipts([day], root=tmp_path)


def test_legacy_control_keeps_current_hash_guard_and_historical_exception(tmp_path: Path) -> None:
    day = _control(tmp_path, snapshots=False)
    _verify_control_receipts([day], root=tmp_path)
    (tmp_path / BOOK_T_CONTROL_ARTIFACT_PATHS["positions"]).write_bytes(b"changed")
    with pytest.raises(BookTShadowError, match="hash mismatch"):
        _verify_control_receipts([day], root=tmp_path)
    _verify_control_receipts([day], root=tmp_path, check_current_artifacts=False)

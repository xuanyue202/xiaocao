"""Account & position I/O — the single source for real-money accounting state.

This logic was duplicated, with already-divergent signatures, between
scripts/live_monitor.py and kronos_screen/scripts/paper_record.py. Two copies of
the load/save/append logic for the book A/B ledger is the most dangerous kind of
duplication: a drift here silently breaks reconciliation. Both scripts now call
these functions so there is one tested implementation. Behaviour is identical to
the former paper_record (parametrized) version. See docs/OPERATING_CONTRACT.md §3.
"""
from __future__ import annotations

import json
import fcntl
import hashlib
import os
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

VALID_BOOKS = frozenset({"A", "B", "T"})


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_account(path: Path, initial_capital: float, fee_rate: float) -> dict[str, Any]:
    """Load a paper account, filling defaults; create a fresh one if absent."""
    if path.exists():
        with path.open(encoding="utf-8") as f:
            account = json.load(f)
        account.setdefault("initial_capital", initial_capital)
        account.setdefault("cash", initial_capital)
        account.setdefault("fee_rate", fee_rate)
        account.setdefault("realized_pnl", 0.0)
        account.setdefault("total_fees", 0.0)
        return account
    return {
        "initial_capital": initial_capital,
        "cash": initial_capital,
        "fee_rate": fee_rate,
        "realized_pnl": 0.0,
        "total_fees": 0.0,
        "created_at": now_iso(),
    }


def save_account(account: dict[str, Any], path: Path) -> None:
    """Atomically persist the account (tmp + replace), stamping updated_at."""
    path.parent.mkdir(parents=True, exist_ok=True)
    account["updated_at"] = now_iso()
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(account, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def append_jsonl(record: dict[str, Any], path: Path) -> None:
    """Append one record to a jsonl audit stream (trades, etc.)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def require_explicit_book(record: dict[str, Any], *, kind: str) -> str:
    """Return a valid explicit ledger book or fail closed.

    Ledger ownership is accounting identity, not a display default.  Never
    infer Book B at the write boundary: historical inference belongs in an
    auditable one-off repair.
    """
    if "book" not in record or record.get("book") in (None, ""):
        raise ValueError(f"{kind} requires an explicit book")
    book = str(record["book"])
    if book not in VALID_BOOKS:
        raise ValueError(f"{kind} has invalid book {book!r}; expected one of {sorted(VALID_BOOKS)}")
    return book


def append_trade(record: dict[str, Any], path: Path) -> None:
    """Append a trade only when its accounting book is explicit and valid."""
    require_explicit_book(record, kind="trade")
    append_jsonl(record, path)


def position_jsonl_line(record: dict[str, Any]) -> str:
    """Serialize one validated position for an append-only ledger writer."""
    require_explicit_book(record, kind="position")
    return json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"


@contextmanager
def ledger_lock(path: Path):
    """Serialize a paper-ledger read/modify/write transaction across processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def ledger_lock_path(live_dir: Path) -> Path:
    """Canonical cross-process lock shared by every paper-ledger writer."""
    return live_dir / "paper_ledger.lock"


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def _install_staged_file(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".txn.tmp")
    shutil.copyfile(staged, tmp)
    tmp.replace(target)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _pending_transaction_path(live_dir: Path) -> Path:
    return live_dir / ".ledger_txn" / "pending.json"


def recover_ledger_transaction(live_dir: Path) -> bool:
    """Finish a prepared multi-file ledger commit after an interrupted writer.

    Call only while holding the canonical ledger lock. Re-installing every
    staged target is idempotent, including when the prior process replaced one
    or two files before it stopped.
    """
    pending = _pending_transaction_path(live_dir)
    if not pending.exists():
        return False
    manifest = json.loads(pending.read_text(encoding="utf-8"))
    files = manifest.get("files") or []
    if not files:
        raise RuntimeError(f"invalid pending ledger transaction: {pending}")
    for item in files:
        staged = Path(str(item["staged"]))
        target = Path(str(item["target"]))
        content = staged.read_bytes()
        if _sha256_bytes(content) != str(item["sha256"]):
            raise RuntimeError(f"staged ledger transaction hash mismatch: {staged}")
        _install_staged_file(staged, target)
    for item in files:
        target = Path(str(item["target"]))
        if _sha256_bytes(target.read_bytes()) != str(item["sha256"]):
            raise RuntimeError(f"ledger recovery target hash mismatch: {target}")
    pending.unlink()
    for item in files:
        Path(str(item["staged"])).unlink(missing_ok=True)
    return True


def commit_ledger_transaction(
    *,
    live_dir: Path,
    positions: list[dict[str, Any]],
    positions_path: Path,
    account: dict[str, Any],
    account_path: Path,
    new_trades: list[dict[str, Any]],
    trades_path: Path,
) -> None:
    """Recoverably commit positions, one account, and appended trades.

    The caller must hold ``ledger_lock(ledger_lock_path(live_dir))``. A durable
    pending manifest is written before replacing any target; an interrupted
    commit is completed by ``recover_ledger_transaction`` on the next writer.
    """
    for position in positions:
        require_explicit_book(position, kind="position")
    for trade in new_trades:
        require_explicit_book(trade, kind="trade")
    account["updated_at"] = now_iso()
    positions_bytes = b"".join(position_jsonl_line(row).encode("utf-8") for row in positions)
    account_bytes = (
        json.dumps(account, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    existing_trades = trades_path.read_bytes() if trades_path.exists() else b""
    if existing_trades and not existing_trades.endswith(b"\n"):
        existing_trades += b"\n"
    trade_bytes = existing_trades + b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for row in new_trades
    )
    payloads = (
        ("positions", positions_path, positions_bytes),
        ("account", account_path, account_bytes),
        ("trades", trades_path, trade_bytes),
    )
    commit_file_transaction(live_dir=live_dir, payloads=list(payloads))


def commit_file_transaction(
    *,
    live_dir: Path,
    payloads: list[tuple[str, Path, bytes]],
) -> None:
    """Recoverably replace an arbitrary set of files under one ledger lock."""
    if not payloads:
        raise ValueError("ledger file transaction requires at least one payload")
    txn_id = uuid.uuid4().hex
    stage_dir = live_dir / ".ledger_txn"
    files = []
    for label, target, content in payloads:
        staged = stage_dir / f"{txn_id}.{label}"
        _atomic_write_bytes(staged, content)
        files.append({
            "label": label,
            "target": str(target.resolve()),
            "staged": str(staged.resolve()),
            "sha256": _sha256_bytes(content),
        })
    manifest = {
        "schema_version": 1,
        "transaction_id": txn_id,
        "state": "prepared",
        "files": files,
    }
    _atomic_write_bytes(
        _pending_transaction_path(live_dir),
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    recover_ledger_transaction(live_dir)


def encode_jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for row in rows
    )


def encode_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def append_jsonl_bytes(path: Path, records: list[dict[str, Any]]) -> bytes:
    content = path.read_bytes() if path.exists() else b""
    if content and not content.endswith(b"\n"):
        content += b"\n"
    return content + encode_jsonl(records)


def load_positions(path: Path) -> list[dict[str, Any]]:
    """Load all position records (skips blank and #-comment lines; tolerates
    malformed lines). Callers filter by book/status as needed."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
    return out


def save_positions(positions: list[dict[str, Any]], path: Path) -> None:
    """Atomically replace the complete position ledger."""
    for position in positions:
        require_explicit_book(position, kind="position")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for position in positions:
            handle.write(json.dumps(position, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)


def position_key(position: dict[str, Any]) -> tuple[str, str]:
    return str(position.get("entry_date", "")), str(position.get("code", ""))

#!/usr/bin/env python3
"""Auditably backfill missing paper-ledger book labels.

Only identities that can be proved from a Book-B-only writer source or a
unique matching position are changed.  Unknown or ambiguous rows fail closed;
the script never treats a missing label as Book B merely because it is old.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import accounts  # noqa: E402


BOOK_B_ONLY_SOURCES = frozenset({"auto:vb_star", "auto:mode_exec_star"})


def _normal_date(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def _position_book(row: dict[str, Any]) -> str | None:
    if row.get("book"):
        return accounts.require_explicit_book(row, kind="position")
    if str(row.get("source") or "") in BOOK_B_ONLY_SOURCES:
        return "B"
    return None


def _position_index(
    positions: list[dict[str, Any]],
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in positions:
        book = str(row["book"])
        code = str(row.get("code") or "")
        for side, field in (("BUY", "entry_date"), ("SELL", "exit_date")):
            day = _normal_date(row.get(field))
            if code and day:
                index.setdefault((side, code, day), []).append(row)
    return index


def _same_number(left: Any, right: Any, *, tolerance: float = 0.005) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def _books_from_matching_positions(
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> set[str]:
    """Narrow a same-code/day collision using accounting facts.

    Book A and B intentionally hold paired names on the same dates.  Shares,
    executed price and realized PnL are ledger facts that distinguish their
    separate fills; use only exact/numerically-equivalent matches.
    """
    narrowed = candidates
    if row.get("shares") not in (None, ""):
        matching = [p for p in narrowed if _same_number(row.get("shares"), p.get("shares"), tolerance=0)]
        narrowed = matching
    side = str(row.get("side") or "").upper()
    price_field = "entry_price" if side == "BUY" else "exit_price"
    if row.get("price") not in (None, ""):
        matching = [p for p in narrowed if _same_number(row.get("price"), p.get(price_field))]
        narrowed = matching
    if side == "SELL" and row.get("realized_pnl") not in (None, ""):
        matching = [
            p for p in narrowed
            if _same_number(row.get("realized_pnl"), p.get("realized_pnl"))
        ]
        narrowed = matching
    return {str(p["book"]) for p in narrowed}


def plan_backfill(
    positions: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    fixed_positions = deepcopy(positions)
    positions_backfilled = 0
    position_changes: list[dict[str, Any]] = []
    for idx, row in enumerate(fixed_positions):
        inferred = _position_book(row)
        if inferred is None:
            raise RuntimeError(
                f"position[{idx}] cannot prove book: code={row.get('code')} "
                f"entry_date={row.get('entry_date')} source={row.get('source')}"
            )
        if not row.get("book"):
            row["book"] = inferred
            positions_backfilled += 1
            position_changes.append({
                "row_index": idx,
                "code": row.get("code"),
                "entry_date": _normal_date(row.get("entry_date")),
                "inferred_book": inferred,
                "proof": f"exclusive_writer_source:{row.get('source')}",
            })

    index = _position_index(fixed_positions)
    fixed_trades = deepcopy(trades)
    trades_backfilled = 0
    trade_changes: list[dict[str, Any]] = []
    for idx, row in enumerate(fixed_trades):
        if row.get("book"):
            accounts.require_explicit_book(row, kind="trade")
            continue
        source = str(row.get("source") or "")
        if source in BOOK_B_ONLY_SOURCES:
            inferred_books = {"B"}
        else:
            key = (
                str(row.get("side") or "").upper(),
                str(row.get("code") or ""),
                _normal_date(row.get("date") or row.get("ts")),
            )
            candidates = index.get(key, [])
            inferred_books = _books_from_matching_positions(row, candidates)
        if not inferred_books:
            raise RuntimeError(
                f"trade[{idx}] cannot prove book: side={row.get('side')} code={row.get('code')} "
                f"date={row.get('date')} source={source or None}"
            )
        if len(inferred_books) != 1:
            raise RuntimeError(
                f"trade[{idx}] ambiguous book {sorted(inferred_books)}: "
                f"side={row.get('side')} code={row.get('code')} date={row.get('date')}"
            )
        row["book"] = next(iter(inferred_books))
        trades_backfilled += 1
        provided_match_fields = [
            field for field in ("shares", "price", "realized_pnl")
            if row.get(field) not in (None, "")
        ]
        trade_changes.append({
            "row_index": idx,
            "side": str(row.get("side") or "").upper(),
            "code": row.get("code"),
            "date": _normal_date(row.get("date") or row.get("ts")),
            "inferred_book": row["book"],
            "proof": (
                f"exclusive_writer_source:{source}"
                if source in BOOK_B_ONLY_SOURCES
                else "unique_position_identity"
            ),
            "matched_facts": provided_match_fields,
        })

    return fixed_positions, fixed_trades, {
        "positions_backfilled": positions_backfilled,
        "trades_backfilled": trades_backfilled,
        "position_changes": position_changes,
        "trade_changes": trade_changes,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{path}:{line_no}: malformed JSON") from exc
        if not isinstance(row, dict):
            raise RuntimeError(f"{path}:{line_no}: expected an object")
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconstruct_existing_repair_evidence(
    positions: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    *,
    expected_positions: int,
    expected_trades: int,
) -> dict[str, Any]:
    """Reconstruct row identities after an older count/hash-only repair.

    This is deliberately labelled after-the-fact: it cannot recreate deleted
    bytes. It uses the known writer boundary—legacy Book-B buys had exclusive
    sources, while legacy unlabeled sells precede the explicit-book cutover—and
    refuses unless the resulting counts and position facts are exact.
    """
    position_candidates = [
        (idx, row) for idx, row in enumerate(positions)
        if row.get("book") == "B" and str(row.get("source") or "") in BOOK_B_ONLY_SOURCES
    ]
    selected_positions = position_candidates[:expected_positions]
    if len(selected_positions) != expected_positions:
        raise RuntimeError("cannot reconstruct the expected legacy position cohort")

    index = _position_index(positions)
    buy_candidates = [
        (idx, row) for idx, row in enumerate(trades)
        if row.get("book") == "B" and str(row.get("side") or "").upper() == "BUY"
        and str(row.get("source") or "") in BOOK_B_ONLY_SOURCES
    ]
    sell_needed = expected_trades - len(buy_candidates)
    if sell_needed < 0:
        raise RuntimeError("exclusive-source BUY cohort exceeds repaired trade count")
    sell_candidates: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(trades):
        if row.get("book") != "B" or str(row.get("side") or "").upper() != "SELL":
            continue
        key = ("SELL", str(row.get("code") or ""), _normal_date(row.get("date") or row.get("ts")))
        if _books_from_matching_positions(row, index.get(key, [])) == {"B"}:
            sell_candidates.append((idx, row))
        if len(sell_candidates) == sell_needed:
            break
    if len(buy_candidates) + len(sell_candidates) != expected_trades:
        raise RuntimeError("cannot reconstruct the expected legacy trade cohort")

    return {
        "audit_confidence": "reconstructed_after_fact",
        "limitation": "original pre-repair rows were not retained; identities reconstructed from writer lineage",
        "position_changes": [{
            "row_index": idx,
            "code": row.get("code"),
            "entry_date": _normal_date(row.get("entry_date")),
            "inferred_book": "B",
            "proof": f"exclusive_writer_source:{row.get('source')}; legacy cohort order",
        } for idx, row in selected_positions],
        "trade_changes": [{
            "row_index": idx,
            "side": "BUY",
            "code": row.get("code"),
            "date": _normal_date(row.get("date") or row.get("ts")),
            "inferred_book": "B",
            "proof": f"exclusive_writer_source:{row.get('source')}",
        } for idx, row in buy_candidates] + [{
            "row_index": idx,
            "side": "SELL",
            "code": row.get("code"),
            "date": _normal_date(row.get("date") or row.get("ts")),
            "inferred_book": "B",
            "proof": "unique_position_identity; count-constrained reconstructed cohort",
        } for idx, row in sell_candidates],
    }


def supplement_existing_audit(
    *,
    live_dir: Path,
    positions: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    audit_path = live_dir / "ledger_repairs.jsonl"
    audit_rows = _read_jsonl(audit_path)
    parent = next((
        row for row in reversed(audit_rows)
        if row.get("operation") == "backfill_explicit_ledger_books"
    ), None)
    if parent is None:
        raise RuntimeError("no count/hash-only book backfill audit to supplement")
    parent_after = parent.get("after_sha256") or {}
    existing = next((
        row for row in audit_rows
        if row.get("operation") == "backfill_explicit_ledger_books_audit_supplement"
        and row.get("schema_version") == 2
        and row.get("parent_after_sha256") == parent_after
    ), None)
    if existing is not None:
        return existing
    evidence = reconstruct_existing_repair_evidence(
        positions,
        trades,
        expected_positions=int(parent.get("positions_backfilled") or 0),
        expected_trades=int(parent.get("trades_backfilled") or 0),
    )
    supplement = {
        "schema_version": 2,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "operation": "backfill_explicit_ledger_books_audit_supplement",
        "parent_after_sha256": parent_after,
        **evidence,
    }
    accounts.commit_file_transaction(
        live_dir=live_dir,
        payloads=[
            ("repair_audit", audit_path, accounts.append_jsonl_bytes(audit_path, [supplement])),
        ],
    )
    return supplement


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-dir", type=Path, default=ROOT / "output" / "live")
    parser.add_argument("--apply", action="store_true", help="atomically apply the proven repair")
    parser.add_argument(
        "--supplement-existing-audit",
        action="store_true",
        help="append transparent per-row evidence for the earlier count/hash-only repair",
    )
    args = parser.parse_args()

    positions_path = args.live_dir / "positions.jsonl"
    trades_path = args.live_dir / "paper_trades.jsonl"
    lock_path = accounts.ledger_lock_path(args.live_dir)
    with accounts.ledger_lock(lock_path):
        accounts.recover_ledger_transaction(args.live_dir)
        positions = _read_jsonl(positions_path)
        trades = _read_jsonl(trades_path)
        if args.supplement_existing_audit:
            supplement = supplement_existing_audit(
                live_dir=args.live_dir, positions=positions, trades=trades,
            )
            print(json.dumps({
                "operation": supplement["operation"],
                "audit_confidence": supplement["audit_confidence"],
                "position_changes": len(supplement["position_changes"]),
                "trade_changes": len(supplement["trade_changes"]),
            }, ensure_ascii=False, sort_keys=True))
            return
        fixed_positions, fixed_trades, report = plan_backfill(positions, trades)
        counts = {
            "positions_backfilled": report["positions_backfilled"],
            "trades_backfilled": report["trades_backfilled"],
        }
        print(json.dumps({"apply": args.apply, **counts}, ensure_ascii=False, sort_keys=True))
        if not args.apply or not any(counts.values()):
            return
        before = {"positions": _sha256(positions_path), "trades": _sha256(trades_path)}
        positions_bytes = accounts.encode_jsonl(fixed_positions)
        trades_bytes = accounts.encode_jsonl(fixed_trades)
        audit = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "operation": "backfill_explicit_ledger_books",
            **counts,
            "position_changes": report["position_changes"],
            "trade_changes": report["trade_changes"],
            "before_sha256": before,
            "after_sha256": {
                "positions": hashlib.sha256(positions_bytes).hexdigest(),
                "trades": hashlib.sha256(trades_bytes).hexdigest(),
            },
        }
        audit_path = args.live_dir / "ledger_repairs.jsonl"
        accounts.commit_file_transaction(
            live_dir=args.live_dir,
            payloads=[
                ("positions", positions_path, positions_bytes),
                ("trades", trades_path, trades_bytes),
                ("repair_audit", audit_path, accounts.append_jsonl_bytes(audit_path, [audit])),
            ],
        )


if __name__ == "__main__":
    main()

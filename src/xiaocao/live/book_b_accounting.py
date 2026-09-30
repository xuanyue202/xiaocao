"""Book-B accounting from proved source events; no broker or paper writer.

Existing intent/fill/capital validators remain the evidence authority. One
replay supplies every consumer; SQLite commits balanced, cent-valued postings
and immutable observations. A cash mismatch never becomes contributed capital.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from .book_b_capital import digest, number
from .trading_execution import account_writer_lock

CENT = Decimal(".01")
DATABASE = "accounting.sqlite3"
CASH_KINDS = frozenset({"FEE", "DIVIDEND", "INTEREST", "REVERSAL"})


def cents(value) -> int:
    return int(number(value).quantize(CENT) * 100)


def money(value: int) -> str:
    return format(Decimal(value) / 100, ".2f")


@dataclass
class OwnedBook:
    rows: list[dict]
    lots: dict[str, dict]
    cash_by_head: dict[str | None, Decimal]
    entries: list[dict]

    @property
    def head(self) -> str | None:
        return next(reversed(self.cash_by_head))

    @property
    def cash(self) -> Decimal:
        return self.cash_by_head[self.head]


def replay_owned(root: Path, *, initial_capital=30000, fee_rate=.0001) -> OwnedBook:
    """The shared legacy-compatible cash/gross-cost and financial-cost replay."""
    from .book_b_live_lifecycle import (_read_jsonl_strict, _validate_ownership_chain,
        _validate_execution_fill_coverage, _load_intent_index, _sha256)
    rows, _ = _validate_ownership_chain(_read_jsonl_strict(
        Path(root) / "book_b_ownership_evidence.jsonl"))
    _validate_execution_fill_coverage(Path(root), rows)
    intents = _load_intent_index(Path(root))
    cash = number(initial_capital)
    if cash <= 0:
        raise ValueError("LIVE_BOOK_B_INITIAL_CAPITAL_INVALID")
    by_head = {None: cash}
    lots, entries = {}, []
    for event in rows:
        intent = intents.get(event["plan_id"])
        if (event.get("logical_account_id") != "primary" or intent is None
                or _sha256(intent) != event["plan_hash"]):
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_PLAN_INTENT_UNPROVEN")
        rate = number(intent.get("fee_rate", fee_rate))
        shares, notional = int(event["shares"]), number(event["fill_notional"])
        if not 0 <= rate < 1 or shares <= 0 or notional <= 0:
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_FILL_INVALID")
        before = cents(cash)
        side = event["side"]
        if side == "BUY":
            lot_id = event["plan_id"]
            lot = lots.setdefault(lot_id, {"owned_lot_id": lot_id,
                "code": event["code"], "name": event.get("name") or event["code"],
                "entry_date": event["trade_date"][:10], "shares": 0,
                "cost": Decimal(0), "cost_cents": 0, "fee_rate": rate,
                "buy_fee_rate": rate, "sell_fee_rate": rate,
                "snapshot_ref": intent.get("snapshot_ref") or ""})
            if (not lot["snapshot_ref"] or lot["snapshot_ref"] != intent.get("snapshot_ref")
                    or lot["code"] != event["code"]):
                raise ValueError("LIVE_BOOK_B_BUY_SNAPSHOT_REF_UNPROVEN")
            cash -= notional * (1 + rate)
            cash_delta = cents(cash) - before
            cost_delta = -cash_delta
            lot["shares"] += shares
            lot["cost"] += notional
        elif side == "SELL":
            lot_id = event.get("owned_lot_id") or intent.get("owned_lot_id") or ""
            lot = lots.get(lot_id)
            if lot is None or lot["code"] != event["code"] or lot["shares"] < shares:
                raise ValueError("LIVE_BOOK_B_SELL_OWNED_LOT_UNPROVEN")
            # Final sale consumes the exact residual cent; partial sales use
            # the same average-cost convention as the existing owned-lot code.
            cost_delta = -(lot["cost_cents"] if shares == lot["shares"] else
                int((Decimal(lot["cost_cents"]) * shares / lot["shares"]).quantize(Decimal(1))))
            lot["cost"] -= lot["cost"] / lot["shares"] * shares
            lot["shares"] -= shares
            cash += notional * (1 - rate)
            cash_delta = cents(cash) - before
        else:
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_SIDE_INVALID")
        lot["cost_cents"] += cost_delta
        pnl = cash_delta + cost_delta
        fee = -cash_delta - cents(notional) if side == "BUY" else cents(notional) - cash_delta
        lines = {"cash": cash_delta, "inventory:" + lot_id: cost_delta, "pnl": -pnl}
        entries.append({"source_id": "fill:" + event["event_hash"], "kind": side,
            "observed_at": event["ts"], "source_hash": event["event_hash"],
            "source": event, "code": event["code"], "lot_id": lot_id,
            "shares": shares, "fee_cents": fee, "fee_basis": "estimated_plan_rate",
            "lines": lines, "realized_pnl_cents": pnl,
            "intent_sha256": event["plan_hash"]})
        by_head[event["event_hash"]] = cash
    return OwnedBook(rows, lots, by_head, entries)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entries(
    seq INTEGER PRIMARY KEY, source_id TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL, previous_hash TEXT, entry_hash TEXT NOT NULL UNIQUE,
    posted INTEGER NOT NULL DEFAULT 0 CHECK(posted IN (0,1)));
CREATE TABLE IF NOT EXISTS postings(
    entry_seq INTEGER NOT NULL REFERENCES entries(seq), account TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer'),
    PRIMARY KEY(entry_seq, account));
CREATE TABLE IF NOT EXISTS observations(
    receipt_sha256 TEXT PRIMARY KEY, observed_at TEXT NOT NULL, body TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS balance_before_post BEFORE UPDATE OF posted ON entries
WHEN NEW.posted=1 AND (SELECT coalesce(sum(amount_cents),0) FROM postings WHERE entry_seq=NEW.seq)!=0
BEGIN SELECT RAISE(ABORT, 'unbalanced accounting entry'); END;
CREATE TRIGGER IF NOT EXISTS immutable_entry_update BEFORE UPDATE ON entries WHEN OLD.posted=1
BEGIN SELECT RAISE(ABORT, 'immutable accounting entry'); END;
CREATE TRIGGER IF NOT EXISTS immutable_entry_delete BEFORE DELETE ON entries
BEGIN SELECT RAISE(ABORT, 'immutable accounting entry'); END;
CREATE TRIGGER IF NOT EXISTS immutable_posting_insert BEFORE INSERT ON postings
WHEN (SELECT posted FROM entries WHERE seq=NEW.entry_seq)=1
BEGIN SELECT RAISE(ABORT, 'immutable accounting posting'); END;
CREATE TRIGGER IF NOT EXISTS immutable_posting_update BEFORE UPDATE ON postings
WHEN (SELECT posted FROM entries WHERE seq=OLD.entry_seq)=1
BEGIN SELECT RAISE(ABORT, 'immutable accounting posting'); END;
CREATE TRIGGER IF NOT EXISTS immutable_posting_delete BEFORE DELETE ON postings
BEGIN SELECT RAISE(ABORT, 'immutable accounting posting'); END;
CREATE TRIGGER IF NOT EXISTS immutable_observation_update BEFORE UPDATE ON observations
BEGIN SELECT RAISE(ABORT, 'immutable accounting observation'); END;
CREATE TRIGGER IF NOT EXISTS immutable_observation_delete BEFORE DELETE ON observations
BEGIN SELECT RAISE(ABORT, 'immutable accounting observation'); END;
"""


@contextmanager
def _database(root: Path):
    path = Path(root) / DATABASE
    if path.is_symlink():
        raise ValueError("BOOK_B_ACCOUNTING_SYMLINK_UNPROVEN")
    path.parent.mkdir(parents=True, exist_ok=True)
    with account_writer_lock(path.parent / "account_writer_locks", "primary"):
        db = sqlite3.connect(path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("BOOK_B_ACCOUNTING_SCHEMA_UNSUPPORTED")
            db.executescript(_SCHEMA)
            db.execute("PRAGMA user_version=1")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def _post(db, body: dict) -> str:
    lines = body["lines"]
    if not lines or any(type(v) is not int for v in lines.values()) or sum(lines.values()) != 0:
        raise ValueError("BOOK_B_ACCOUNTING_UNBALANCED")
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    existing = db.execute("SELECT body,entry_hash FROM entries WHERE source_id=?",
                          (body["source_id"],)).fetchone()
    if existing:
        if existing[0] != encoded:
            raise ValueError("BOOK_B_ACCOUNTING_SOURCE_CONFLICT")
        return existing[1]
    row = db.execute("SELECT entry_hash FROM entries ORDER BY seq DESC LIMIT 1").fetchone()
    previous = row[0] if row else None
    head = digest({"body": body, "previous_hash": previous})
    cursor = db.execute("INSERT INTO entries(source_id,body,previous_hash,entry_hash) VALUES(?,?,?,?)",
                        (body["source_id"], encoded, previous, head))
    db.executemany("INSERT INTO postings VALUES(?,?,?)",
                   [(cursor.lastrowid, key, value) for key, value in lines.items()])
    db.execute("UPDATE entries SET posted=1 WHERE seq=?", (cursor.lastrowid,))
    return head


def _entries(db, *, through: str | None = None) -> list[dict]:
    result, previous = [], None
    by_hash, reversed_entries = {}, set()
    for seq, encoded, predecessor, head, posted in db.execute(
            "SELECT seq,body,previous_hash,entry_hash,posted FROM entries ORDER BY seq"):
        body = json.loads(encoded)
        lines = dict(db.execute("SELECT account,amount_cents FROM postings WHERE entry_seq=?", (seq,)))
        if (posted != 1 or predecessor != previous or lines != body["lines"]
                or sum(lines.values()) != 0 or digest({"body": body, "previous_hash": previous}) != head):
            raise ValueError("BOOK_B_ACCOUNTING_JOURNAL_INVALID")
        if body["kind"] == "REVERSAL":
            target_hash = body.get("reverses_entry_sha256")
            target = by_hash.get(target_hash)
            if (target is None or target["kind"] not in CASH_KINDS - {"REVERSAL"}
                    or target_hash in reversed_entries
                    or lines != {key: -amount for key, amount in target["lines"].items()}):
                raise ValueError("BOOK_B_ACCOUNTING_REVERSAL_INVALID")
            reversed_entries.add(target_hash)
        result.append({**body, "entry_hash": head})
        by_hash[head] = body
        previous = head
        if through == head:
            return result
    if through is not None:
        raise ValueError("BOOK_B_ACCOUNTING_HEAD_UNPROVEN")
    return result


def _identity(db, root: Path, initial_capital) -> None:
    from .book_b_capital import policy
    cfg = policy(root)
    expected = {"book": "B", "logical_account_id": "primary", "environment": "app_server_simulation",
        "opening_capital_cents": str(cents(initial_capital)),
        "opening_basis": "legacy_strategy_seed_not_whole_account_deposit"}
    if cfg:
        expected["fund_account_binding_sha256"] = cfg["fund_account_binding_sha256"]
    for key, value in expected.items():
        old = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        if old and old[0] != value:
            raise ValueError("BOOK_B_ACCOUNTING_IDENTITY_MISMATCH")
        db.execute("INSERT OR IGNORE INTO metadata VALUES(?,?)", (key, value))


def _sync(db, root: Path, book: OwnedBook, *, initial_capital=30000) -> list[dict]:
    from .book_b_capital import flows
    _identity(db, root, initial_capital)
    opening = cents(initial_capital)
    source = [{"source_id": "opening:legacy", "kind": "OPENING", "observed_at": None,
        "source_hash": digest({"legacy_strategy_seed": money(opening)}),
        "lines": {"cash": opening, "capital": -opening}}]
    capital_by_owner = {}
    for flow in flows(root):
        amount = cents(flow["amount"])
        capital_by_owner.setdefault(flow["ownership_head_sha256"], []).append({
            "source_id": "capital:" + flow["event_hash"], "kind": "CAPITAL",
            "observed_at": flow["observed_at"], "source_hash": flow["event_hash"],
            "source": flow, "classification_basis": flow.get("classification_basis", "legacy_approved_policy"),
            "lines": {"cash": amount, "capital": -amount}})
    source.extend(capital_by_owner.get(None, []))
    for entry in book.entries:
        source.append(entry)
        source.extend(capital_by_owner.get(entry["source_hash"], []))
    # Existing JSONL files are immutable input evidence, not a second
    # financial posting engine. Reject missing/changed already-imported facts.
    identifiers = {e["source_id"] for e in source}
    previous = _entries(db)
    if any(e["source_id"] not in identifiers for e in previous if e["kind"] in {"OPENING", "BUY", "SELL", "CAPITAL"}):
        raise ValueError("BOOK_B_ACCOUNTING_SOURCE_REGRESSION")
    for entry in source:
        _post(db, entry)
    return _entries(db)


def _balances(entries: list[dict]) -> dict[str, int]:
    totals = {}
    for event in entries:
        for account, amount in event["lines"].items():
            totals[account] = totals.get(account, 0) + amount
    return totals


def sync_journal(root: Path, *, initial_capital=30000) -> dict:
    """Idempotently import all proved source facts in one database transaction."""
    root = Path(root)
    with _database(root) as db:
        book = replay_owned(root, initial_capital=initial_capital)
        entries = _sync(db, root, book, initial_capital=initial_capital)
        totals = _balances(entries)
        return {"database_path": str(root / DATABASE), "entry_count": len(entries),
            "journal_head_sha256": entries[-1]["entry_hash"],
            "ledger_cash": money(totals.get("cash", 0)),
            "net_contributed_capital": money(-totals.get("capital", 0)),
            "realized_pnl": money(-totals.get("pnl", 0))}


def observe_account(root: Path, *, cash, market_value, liquidation_value, snapshot: dict,
                    capital_state: dict, initial_capital=30000) -> dict:
    """Store a hash-bound valuation; unclassified cash makes total PnL N/A."""
    root = Path(root)
    with _database(root) as db:
        cash_event_head(root, no_later_than=snapshot["observed_at"])
        book = replay_owned(root, initial_capital=initial_capital)
        entries = _sync(db, root, book, initial_capital=initial_capital)
        from .book_b_capital import POLICY, has_open_buy, has_open_buy_with_possible_effect
        cash_basis = ("owned_replay_including_buy_reserve" if has_open_buy(root) else
            "app_available_cash" if capital_state["capital_policy_id"] == POLICY else "legacy_owned_cash_replay")
        binding = snapshot["fund_account_binding_sha256"]
        previous = db.execute("SELECT value FROM metadata WHERE key='fund_account_binding_sha256'").fetchone()
        if previous and previous[0] != binding:
            raise ValueError("BOOK_B_ACCOUNTING_IDENTITY_MISMATCH")
        db.execute("INSERT OR IGNORE INTO metadata VALUES('fund_account_binding_sha256',?)", (binding,))
        totals = _balances(entries)
        inventory = sum(v for k, v in totals.items() if k.startswith("inventory:"))
        actual, exposure, liquidation = cents(cash), cents(market_value), cents(liquidation_value)
        broker_available = cents(
            snapshot["available_cash"] if snapshot.get("schema_version") == "book-b-buy-preflight.v1"
            else snapshot["funds_summary"]["available_cash"]
        )
        risk_cash = min(actual, totals.get("cash", 0))
        if cash_basis == "owned_replay_including_buy_reserve" and not has_open_buy_with_possible_effect(root):
            # A bare intent has no APP reserve; a lower fresh available cash
            # is a real conservative loss until its economic source is known.
            risk_cash = min(risk_cash, broker_available)
        difference = actual - totals.get("cash", 0)
        contributed = -totals.get("capital", 0)
        realized, unrealized = -totals.get("pnl", 0), exposure - inventory
        nav = actual + exposure
        reconciled = difference == 0 and cash_basis != "owned_replay_including_buy_reserve"
        status = ("cash_reserve_reconciliation_required" if cash_basis == "owned_replay_including_buy_reserve" else
                  "reconciled" if reconciled else "cash_reconciliation_required")
        if difference == 0 and nav - contributed != realized + unrealized:
            raise ValueError("BOOK_B_ACCOUNTING_PNL_EQUATION_INVALID")
        body = {"schema_version": "book-b-accounting.v1", "book": "B",
            "environment": "app_server_simulation", "logical_account_id": "primary",
            "fund_account_binding_sha256": snapshot["fund_account_binding_sha256"],
            "observed_at": snapshot["observed_at"], "broker_snapshot_sha256": snapshot["snapshot_sha256"],
            "ownership_head_sha256": book.head, "capital_flow_head_sha256": capital_state["capital_flow_head_sha256"],
            "journal_head_sha256": entries[-1]["entry_hash"], "entry_count": len(entries),
            "status": status,
            "cash_basis": cash_basis, "fee_basis": "estimated_plan_rate",
            "broker_available_cash": money(broker_available),
            "opening_capital": money(cents(initial_capital)), "cash": money(actual),
            "ledger_cash": money(totals.get("cash", 0)),
            "cash_difference": None if cash_basis == "owned_replay_including_buy_reserve" else money(difference),
            "net_contributed_capital": money(contributed), "marked_nav": money(nav),
            "owned_market_value": money(exposure),
            "liquidation_nav": money(actual + liquidation),
            "estimated_exit_fee": money(exposure - liquidation),
            "remaining_cost": money(inventory), "realized_pnl": money(realized),
            "unrealized_pnl": money(unrealized),
            "cumulative_pnl": money(nav - contributed) if reconciled else None,
            "risk_unit_factor": capital_state["capital_unit_factor"],
            # A positive unclassified difference cannot raise the risk high
            # water. A negative difference remains a conservative loss.
            "conservative_risk_nav": str((Decimal(risk_cash + liquidation)
                / 100 / number(capital_state["capital_unit_factor"])).quantize(Decimal(".000001"))),
            "lots": [{"owned_lot_id": k, "code": v["code"], "shares": v["shares"],
                      "remaining_cost": money(v["cost_cents"])} for k, v in book.lots.items() if v["shares"] > 0]}
        body["receipt_sha256"] = digest(body)
        encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        old = db.execute("SELECT body FROM observations WHERE receipt_sha256=?", (body["receipt_sha256"],)).fetchone()
        if old and old[0] != encoded:
            raise ValueError("BOOK_B_ACCOUNTING_OBSERVATION_CONFLICT")
        db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?)",
                   (body["receipt_sha256"], datetime.fromisoformat(body["observed_at"]).astimezone(
                       timezone.utc).isoformat(timespec="microseconds"), encoded))
        return body


def verify_observation(root: Path, report: dict, *, current: bool = False) -> dict:
    body = {k: v for k, v in report.items() if k != "receipt_sha256"}
    if digest(body) != report.get("receipt_sha256"):
        raise ValueError("BOOK_B_ACCOUNTING_OBSERVATION_INVALID")
    path = (Path(root) / DATABASE).absolute()
    if not path.is_file() or path.is_symlink():
        raise ValueError("BOOK_B_ACCOUNTING_DATABASE_REQUIRED")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        saved = db.execute("SELECT body FROM observations WHERE receipt_sha256=?", (report["receipt_sha256"],)).fetchone()
        if saved is None or json.loads(saved[0]) != report:
            raise ValueError("BOOK_B_ACCOUNTING_OBSERVATION_UNPROVEN")
        entries = _entries(db, through=report["journal_head_sha256"])
        totals = _balances(entries)
        if (len(entries) != report["entry_count"] or money(totals.get("cash", 0)) != report["ledger_cash"]
                or money(-totals.get("capital", 0)) != report["net_contributed_capital"]
                or money(-totals.get("pnl", 0)) != report["realized_pnl"]):
            raise ValueError("BOOK_B_ACCOUNTING_OBSERVATION_BALANCE_MISMATCH")
        if current:
            from .book_b_capital import current_flow_state
            if (_entries(db)[-1]["entry_hash"] != report["journal_head_sha256"]
                    or replay_owned(root).head != report["ownership_head_sha256"]
                    or current_flow_state(root)["capital_flow_head_sha256"] != report["capital_flow_head_sha256"]):
                raise ValueError("BOOK_B_ACCOUNTING_OBSERVATION_SOURCE_CHANGED")
            cash_event_head(root, no_later_than=report["observed_at"])
        return report


def details(root: Path) -> list[dict]:
    """Cumulative statement, derived from the same immutable postings."""
    path = (Path(root) / DATABASE).absolute()
    if not path.exists() or path.is_symlink():
        raise ValueError("BOOK_B_ACCOUNTING_DATABASE_REQUIRED")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        entries = _entries(db)
    running, result = 0, []
    for event in entries:
        lines = event["lines"]
        running += lines.get("cash", 0)
        source = event.get("source", {})
        result.append({"event_id": event["source_id"], "observed_at": event["observed_at"],
            "trade_date": source.get("trade_date", ""), "book": "B", "logical_account_id": "primary",
            "environment": "app_server_simulation", "owned_lot_id": event.get("lot_id", ""),
            "source_event_id": source.get("event_id", ""),
            "source_execution_event_id": source.get("source_execution_event_id", ""),
            "native_trade_id": source.get("native_trade_id"),
            "fill_price": source.get("fill_price", ""), "fill_notional": source.get("fill_notional", ""),
            "confirmation_status": ("legacy_strategy_seed" if event["kind"] == "OPENING"
                                    else "source_proven_posted"), "trade_time": source.get("trade_time"),
            "reverses_entry_sha256": event.get("reverses_entry_sha256", ""),
            "kind": event["kind"], "code": event.get("code", ""),
            "order_id": source.get("broker_order_id", ""), "shares": event.get("shares", 0),
            "fee": money(event.get("fee_cents", 0)), "fee_basis": event.get("fee_basis", ""),
            "cash_change": money(lines.get("cash", 0)), "ledger_cash_after": money(running),
            "cost_change": money(sum(v for k, v in lines.items() if k.startswith("inventory:"))),
            "net_contributed_change": money(-lines.get("capital", 0)),
            "realized_pnl": money(-lines.get("pnl", 0)), "source_sha256": event["source_hash"],
            "entry_sha256": event["entry_hash"]})
    return result


def latest_observation(root: Path) -> dict | None:
    path = (Path(root) / DATABASE).absolute()
    if not path.exists():
        return None
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute("SELECT body FROM observations ORDER BY observed_at DESC,rowid DESC LIMIT 1").fetchone()
    return verify_observation(root, json.loads(row[0])) if row else None


def cash_adjustment(root: Path, *, through: str | None = None, as_of: str | None = None) -> Decimal:
    """Only typed non-capital cash facts; never infer an event from a balance."""
    path = (Path(root) / DATABASE).absolute()
    if not path.exists():
        if through is not None:
            raise ValueError("BOOK_B_ACCOUNTING_CASH_EVENT_HEAD_UNPROVEN")
        return Decimal(0)
    if path.is_symlink():
        raise ValueError("BOOK_B_ACCOUNTING_SYMLINK_UNPROVEN")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        rows = _entries(db, through=through)
    return Decimal(sum(e["lines"].get("cash", 0) for e in rows
        if e["kind"] in CASH_KINDS
        and (as_of is None or datetime.fromisoformat(e["observed_at"]) <= datetime.fromisoformat(as_of)))) / 100


def cash_event_head(root: Path, *, no_later_than: str | None = None) -> str | None:
    path = (Path(root) / DATABASE).absolute()
    if not path.exists():
        return None
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        events = [e for e in _entries(db) if e["kind"] in CASH_KINDS]
        if no_later_than and any(datetime.fromisoformat(e["observed_at"]) > datetime.fromisoformat(no_later_than)
                                 for e in events):
            raise ValueError("BOOK_B_ACCOUNTING_CASH_SNAPSHOT_REGRESSION")
        return events[-1]["entry_hash"] if events else None


def record_cash_event(root: Path, proof: dict, *, now: datetime | None = None) -> dict:
    """Post an exact account-bound native cash-statement row, not guessed fees.

    The caller supplies a proved statement receipt. The normal APP port does
    not yet capture these rows; absent evidence remains reconciliation-only.
    A standalone fee row is additional to model trade fees, not a replacement
    commission total. Dividend ownership must be independently proved.
    """
    from .book_b_live_lifecycle import validate_broker_account_snapshot, _normalize_code, _broker_integer
    from .book_b_capital import policy
    root = Path(root)
    observed = now or datetime.now(timezone.utc)
    snapshot = proof["broker_snapshot"]
    validate_broker_account_snapshot(snapshot, trade_date=snapshot["trade_date"], now=observed)
    cfg = policy(root)
    if cfg is None or cfg["fund_account_binding_sha256"] != snapshot["fund_account_binding_sha256"]:
        raise ValueError("BOOK_B_ACCOUNTING_CASH_EVENT_ACCOUNT_UNPROVEN")
    statement = proof["statement"]
    body = {k: v for k, v in statement.items() if k != "receipt_sha256"}
    if (statement.get("schema_version") != "foundersc-native-cash-statement.v1"
            or statement.get("source") != "foundersc_native_app"
            or statement.get("account_binding") != "proven"
            or statement.get("fund_account_binding_sha256") != snapshot["fund_account_binding_sha256"]
            or statement.get("observed_at") != snapshot["observed_at"]
            or statement.get("receipt_sha256") != digest(body)):
        raise ValueError("BOOK_B_ACCOUNTING_CASH_STATEMENT_UNPROVEN")
    rows = statement.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("BOOK_B_ACCOUNTING_CASH_STATEMENT_UNPROVEN")
    matches = [r for r in rows if r.get("event_id") == proof.get("event_id")]
    if len(matches) != 1:
        raise ValueError("BOOK_B_ACCOUNTING_CASH_EVENT_NOT_UNIQUE")
    event = matches[0]
    kind, amount = event.get("kind"), number(event.get("amount"))
    if (not isinstance(event.get("event_id"), str) or not event["event_id"].strip()
            or kind not in CASH_KINDS or amount == 0
            or amount != amount.quantize(CENT)
            or (kind == "FEE" and (amount >= 0 or event.get("fee_basis") != "additional_non_trade_charge"))
            or (kind in {"DIVIDEND", "INTEREST"} and amount <= 0)):
        raise ValueError("BOOK_B_ACCOUNTING_CASH_EVENT_INVALID")
    with _database(root) as db:
        book = replay_owned(root)
        _sync(db, root, book)
        if kind == "DIVIDEND":
            lot = book.lots.get(event.get("owned_lot_id"))
            entitlement = proof.get("entitlement_snapshot")
            if lot is None or event.get("code") != lot["code"] or not isinstance(entitlement, dict):
                raise ValueError("BOOK_B_ACCOUNTING_DIVIDEND_OWNERSHIP_UNPROVEN")
            stamp = datetime.fromisoformat(entitlement["observed_at"])
            validate_broker_account_snapshot(entitlement, trade_date=entitlement["trade_date"], now=stamp)
            owned = sum((1 if row["side"] == "BUY" else -1) * row["shares"] for row in book.rows
                if row["code"] == event["code"] and datetime.fromisoformat(row["ts"]) <= stamp)
            positions = [r for r in entitlement["tables"]["positions"]["rows"]
                         if _normalize_code(r["证券代码"]) == _normalize_code(event["code"])]
            if (entitlement["fund_account_binding_sha256"] != snapshot["fund_account_binding_sha256"]
                    or event.get("entitlement_trade_date") != entitlement["trade_date"]
                    or stamp > datetime.fromisoformat(snapshot["observed_at"])
                    or len(positions) != 1 or owned <= 0
                    or owned != _broker_integer(positions[0]["证券数量"], reason="DIVIDEND_ENTITLEMENT_INVALID")):
                raise ValueError("BOOK_B_ACCOUNTING_DIVIDEND_OWNERSHIP_UNPROVEN")
        if kind == "INTEREST":
            try:
                start = datetime.fromisoformat(event["period_start"])
                end = datetime.fromisoformat(event["period_end"])
                approved = datetime.fromisoformat(cfg["approved_at"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("BOOK_B_ACCOUNTING_INTEREST_OWNERSHIP_UNPROVEN") from exc
            if (event.get("interest_basis") != "available_cash" or start.tzinfo is None
                    or end.tzinfo is None or approved.tzinfo is None
                    or not approved <= start < end <= datetime.fromisoformat(snapshot["observed_at"])):
                raise ValueError("BOOK_B_ACCOUNTING_INTEREST_OWNERSHIP_UNPROVEN")
        entry = {"source_id": "cash:" + statement["fund_account_binding_sha256"] + ":" + event["event_id"],
            "kind": kind, "observed_at": statement["observed_at"],
            "source_hash": digest({"statement": statement, "event_id": event["event_id"]}),
            "source": proof, "event": event, "code": event.get("code", ""),
            "fee_basis": event.get("fee_basis", "native_statement"),
            "lines": {"cash": cents(amount), "pnl": -cents(amount)}}
        if kind == "REVERSAL":
            history = _entries(db)
            target_hash = event.get("reverses_entry_sha256")
            target = next((e for e in history if e["entry_hash"] == target_hash), None)
            if (target is None or target["kind"] not in CASH_KINDS - {"REVERSAL"}
                    or cents(amount) != -target["lines"]["cash"]
                    or datetime.fromisoformat(target["observed_at"]) > datetime.fromisoformat(statement["observed_at"])):
                raise ValueError("BOOK_B_ACCOUNTING_REVERSAL_UNPROVEN")
            entry["reverses_entry_sha256"] = target_hash
        old = db.execute("SELECT body,entry_hash FROM entries WHERE source_id=?", (entry["source_id"],)).fetchone()
        if old and json.loads(old[0]).get("event") != event:
            raise ValueError("BOOK_B_ACCOUNTING_SOURCE_CONFLICT")
        if kind == "REVERSAL" and old is None and any(e.get("reverses_entry_sha256") == target_hash for e in history):
            raise ValueError("BOOK_B_ACCOUNTING_REVERSAL_ALREADY_POSTED")
        head = old[1] if old else _post(db, entry)
        return {"status": "cash_event_posted", "event_id": entry["source_id"],
                "amount": money(cents(amount)), "entry_sha256": head}


def backup(root: Path, destination: Path) -> dict:
    """Consistent SQLite backup with integrity and full journal validation."""
    source = (Path(root) / DATABASE).absolute()
    destination = Path(destination).resolve()
    if destination.exists() or destination == source or source.is_symlink():
        raise ValueError("BOOK_B_ACCOUNTING_BACKUP_DESTINATION_EXISTS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".accounting-backup-", dir=destination.parent)
    temporary = Path(temporary_name)
    os.close(fd)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as db, sqlite3.connect(temporary) as copy:
            db.backup(copy)
            if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("BOOK_B_ACCOUNTING_BACKUP_INVALID")
            rows = _entries(copy)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": "backup_verified", "path": str(destination), "entry_count": len(rows),
            "journal_head_sha256": rows[-1]["entry_hash"] if rows else None}

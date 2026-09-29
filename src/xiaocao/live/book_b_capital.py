"""Account-bound APP cash allocation journal; never a paper or fill writer.

Only an explicitly classified allocation creates capital units. A changed
available balance alone stays unexplained cash. While BUY funds are reserved,
replay the existing allocation; fresh available cash independently caps orders.
Funding cannot manufacture profit or reset drawdown.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

POLICY = "book_b_app_available_cash_v1"
SOURCE = "broker_reconciled_book_b_dynamic_nav"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def number(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("BOOK_B_CAPITAL_NUMBER_INVALID")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("BOOK_B_CAPITAL_NUMBER_INVALID")
    return result


def _read(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("BOOK_B_CAPITAL_SYMLINK_UNPROVEN")
    return json.loads(path.read_text(encoding="utf-8"))


def policy(root: Path) -> dict | None:
    path = Path(root) / "capital_policy.json"
    if not path.exists():
        return None
    value = _read(path)
    body = {k: v for k, v in value.items() if k != "policy_sha256"}
    if (value.get("policy_id") != POLICY or value.get("logical_account_id") != "primary"
            or value.get("policy_sha256") != digest(body)
            or len(value.get("fund_account_binding_sha256", "")) != 64):
        raise ValueError("BOOK_B_CAPITAL_POLICY_UNPROVEN")
    return value


def ownership_cash(root: Path) -> dict[str | None, Decimal]:
    from .book_b_accounting import replay_owned
    return replay_owned(root).cash_by_head


def flows(root: Path) -> list[dict]:
    """Validate the whole immutable journal, not only its latest checksum."""
    from .book_b_live_lifecycle import _read_jsonl_strict
    cfg = policy(root)
    rows = _read_jsonl_strict(Path(root) / "capital_flows.jsonl")
    if rows and cfg is None:
        raise ValueError("BOOK_B_CAPITAL_POLICY_REQUIRED")
    cash_by_head = ownership_cash(root)
    indexes = {head: i for i, head in enumerate(cash_by_head)}
    previous = None
    net = absolute = Decimal(0)
    factor = Decimal(1)
    last_index = -1
    stamp = None
    for row in rows:
        body = {k: v for k, v in row.items() if k != "event_hash"}
        owner = row.get("ownership_head_sha256")
        observed = datetime.fromisoformat(row["observed_at"])
        if (row.get("previous_hash") != previous or digest(body) != row.get("event_hash")
                or row.get("policy_id") != POLICY or row.get("logical_account_id") != "primary"
                or row.get("fund_account_binding_sha256") != cfg["fund_account_binding_sha256"]
                or owner not in indexes or indexes[owner] < last_index
                or observed.tzinfo is None or (stamp is not None and observed < stamp)
                or len(row.get("broker_snapshot_sha256", "")) != 64):
            raise ValueError("BOOK_B_CAPITAL_FLOW_CHAIN_INVALID")
        snapshot = _read(Path(root) / "capital_snapshots" / f"{row['broker_snapshot_sha256']}.json")
        if snapshot.get("schema_version") == "book-b-buy-preflight.v1":
            from .buy_preflight import validate_buy_preflight
            validate_buy_preflight(snapshot, snapshot["trade_date"], observed)
        else:
            from .book_b_live_lifecycle import validate_broker_account_snapshot
            validate_broker_account_snapshot(snapshot, trade_date=snapshot["trade_date"], now=observed)
        available = snapshot.get("available_cash", (snapshot.get("funds_summary") or {}).get("available_cash"))
        if (snapshot["snapshot_sha256"] != row["broker_snapshot_sha256"]
                or snapshot["observed_at"] != row["observed_at"]
                or snapshot["fund_account_binding_sha256"] != row["fund_account_binding_sha256"]
                or number(available) != number(row["cash_after"])):
            raise ValueError("BOOK_B_CAPITAL_FLOW_SNAPSHOT_MISMATCH")
        from .book_b_accounting import cash_adjustment
        adjustment = (cash_adjustment(root, through=row["accounting_cash_event_head_sha256"])
                      if row.get("accounting_cash_event_head_sha256") else Decimal(0))
        before = (cash_by_head[owner] + net + adjustment).quantize(Decimal(".01"))
        delta = number(row["amount"])
        after = before + delta
        liquidation = number(row["owned_liquidation_value_after_fee"])
        nav_before = before + liquidation
        nav_after = after + liquidation
        if delta == 0 or liquidation < 0 or nav_before <= 0 or nav_after <= 0 or after < 0:
            raise ValueError("BOOK_B_CAPITAL_FLOW_EQUATION_INVALID")
        net += delta
        absolute += abs(delta)
        factor *= nav_after / nav_before
        checks = {"cash_before": before, "cash_after": after,
            "nav_before": nav_before, "nav_after": nav_after,
            "net_external_flow_total": net, "absolute_external_flow_total": absolute,
            "unit_factor": factor}
        if any(number(row[key]) != value for key, value in checks.items()):
            raise ValueError("BOOK_B_CAPITAL_FLOW_EQUATION_INVALID")
        previous, last_index, stamp = row["event_hash"], indexes[owner], observed
    return rows


def flow_state(root: Path, head: str | None = None) -> dict:
    rows = flows(root)
    if head is None:
        return {"capital_policy_id": "", "capital_flow_head_sha256": None,
            "net_external_flow_total": 0., "external_flow_total": 0., "capital_unit_factor": "1"}
    row = next((r for r in rows if r["event_hash"] == head), None)
    if row is None:
        raise ValueError("BOOK_B_CAPITAL_FLOW_HEAD_UNPROVEN")
    return {"capital_policy_id": POLICY, "capital_flow_head_sha256": head,
        "net_external_flow_total": float(row["net_external_flow_total"]),
        "external_flow_total": float(row["absolute_external_flow_total"]),
        "capital_unit_factor": row["unit_factor"]}


def current_flow_state(root: Path) -> dict:
    rows = flows(root)
    result = flow_state(root, rows[-1]["event_hash"] if rows else None)
    if policy(root) is not None:
        result["capital_policy_id"] = POLICY
    return result


def _net_cash(root: Path, state: dict, *, as_of: str | None = None) -> Decimal:
    """Exact values stay in source facts/SQLite; float fields are compatibility views."""
    from .book_b_accounting import cash_adjustment
    head = state["capital_flow_head_sha256"]
    net = next((number(r["net_external_flow_total"]) for r in flows(root) if r["event_hash"] == head), Decimal(0))
    return net + cash_adjustment(root, as_of=as_of)


def has_open_buy(root: Path) -> bool:
    from .book_b_live_lifecycle import _load_intent_index, open_execution_plan_ids
    intents = _load_intent_index(Path(root))
    return any(intents[p].get("side") == "BUY" for p in open_execution_plan_ids(Path(root)))


def allocate_cash(root: Path, *, base_cash: Decimal, liquidation: float,
                  ownership_head: str | None, snapshot: dict, sync: bool = True,
                  replay_flow_head: str | None = None, historical: bool = False,
                  allocation_reference: str | None = None) -> tuple[Decimal, dict]:
    from .trading_execution import account_writer_lock
    with account_writer_lock(Path(root) / "account_writer_locks", "primary"):
        return _allocate_cash_locked(root, base_cash=base_cash, liquidation=liquidation,
            ownership_head=ownership_head, snapshot=snapshot, sync=sync,
            replay_flow_head=replay_flow_head, historical=historical,
            allocation_reference=allocation_reference)


def _allocate_cash_locked(root: Path, *, base_cash: Decimal, liquidation: float,
                  ownership_head: str | None, snapshot: dict, sync: bool,
                  replay_flow_head: str | None, historical: bool,
                  allocation_reference: str | None) -> tuple[Decimal, dict]:
    cfg = policy(root)
    current = current_flow_state(root)
    if historical:
        if sync:
            raise ValueError("BOOK_B_CAPITAL_HISTORICAL_WRITE_FORBIDDEN")
        current = flow_state(root, replay_flow_head)
        if replay_flow_head is not None:
            current["capital_policy_id"] = POLICY
    cash = (base_cash + _net_cash(root, current, as_of=snapshot["observed_at"])).quantize(Decimal(".01"))
    if cfg is None:
        return cash, current
    if snapshot.get("fund_account_binding_sha256") != cfg["fund_account_binding_sha256"]:
        raise ValueError("BOOK_B_CAPITAL_ACCOUNT_MISMATCH")
    if not sync:
        return cash, current
    path = Path(root) / "capital_flows.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        by_head = ownership_cash(root)
        if next(reversed(by_head)) != ownership_head:
            raise ValueError("BOOK_B_CAPITAL_OWNERSHIP_CHANGED")
        current = current_flow_state(root)
        cash = (base_cash + _net_cash(root, current, as_of=snapshot["observed_at"])).quantize(Decimal(".01"))
        # A frozen BUY is already part of strategy cash: never withdraw it or
        # add it a second time. Capital refresh resumes after reconciliation.
        if has_open_buy(root):
            return cash, current
        available = number(snapshot.get("available_cash", (snapshot.get("funds_summary") or {}).get("available_cash")))
        available = available.quantize(Decimal(".01"))
        delta = available - cash
        if delta == 0:
            return cash, current
        if not allocation_reference:
            # Available cash still caps current execution. Its unexplained
            # difference is observed by the journal, never unitized as funding.
            return available, current
        existing = flows(root)
        if existing and datetime.fromisoformat(snapshot["observed_at"]) < datetime.fromisoformat(existing[-1]["observed_at"]):
            raise ValueError("BOOK_B_CAPITAL_SNAPSHOT_REGRESSION")
        nav_before = cash + number(liquidation)
        nav_after = available + number(liquidation)
        if available < 0 or nav_before <= 0 or nav_after <= 0:
            raise ValueError("BOOK_B_CAPITAL_FLOW_NAV_INVALID")
        body = {"policy_id": POLICY, "logical_account_id": "primary",
            "fund_account_binding_sha256": cfg["fund_account_binding_sha256"],
            "ownership_head_sha256": ownership_head,
            "broker_snapshot_sha256": snapshot["snapshot_sha256"],
            "observed_at": snapshot["observed_at"],
            "kind": "app_available_cash_allocation", "amount": str(delta),
            "classification_basis": "operator_approved_strategy_allocation",
            "approval_reference": allocation_reference,
            "cash_before": str(cash), "cash_after": str(available),
            "owned_liquidation_value_after_fee": str(number(liquidation)),
            "nav_before": str(nav_before), "nav_after": str(nav_after),
            "net_external_flow_total": str(sum((number(r["amount"]) for r in existing), Decimal(0)) + delta),
            "absolute_external_flow_total": str(sum((abs(number(r["amount"])) for r in existing), Decimal(0)) + abs(delta)),
            "unit_factor": str(number(current["capital_unit_factor"]) * (nav_after / nav_before)),
            "previous_hash": current["capital_flow_head_sha256"]}
        from .book_b_accounting import cash_event_head
        adjustment_head = cash_event_head(root)
        if adjustment_head is not None:
            body["accounting_cash_event_head_sha256"] = adjustment_head
        body["event_hash"] = digest(body)
        from .book_b_live_lifecycle import _write_json_atomic
        snapshot_path = Path(root) / "capital_snapshots" / f"{snapshot['snapshot_sha256']}.json"
        if snapshot_path.exists():
            if _read(snapshot_path) != snapshot:
                raise ValueError("BOOK_B_CAPITAL_SNAPSHOT_IMMUTABILITY_VIOLATION")
        else:
            _write_json_atomic(snapshot_path, snapshot)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return available, current_flow_state(root)


def verify_account(root: Path, payload: dict) -> Decimal:
    state = flow_state(root, payload.get("capital_flow_head_sha256"))
    cfg = policy(root)
    if payload.get("capital_flow_head_sha256") and (cfg is None or payload.get("capital_policy_id") != POLICY):
        raise ValueError("BOOK_B_CAPITAL_ACCOUNT_POLICY_MISMATCH")
    for key in ("net_external_flow_total", "external_flow_total", "capital_unit_factor"):
        if number(payload.get(key, state[key])) != number(state[key]):
            raise ValueError("BOOK_B_CAPITAL_ACCOUNT_FLOW_MISMATCH")
    cash_by_head = ownership_cash(root)
    head = payload.get("ownership_head_sha256")
    if head not in cash_by_head:
        raise ValueError("BOOK_B_CAPITAL_ACCOUNT_OWNERSHIP_UNPROVEN")
    if payload.get("capital_flow_head_sha256"):
        row = next(r for r in flows(root) if r["event_hash"] == payload["capital_flow_head_sha256"])
        indexes = {h: i for i, h in enumerate(cash_by_head)}
        if (indexes[row["ownership_head_sha256"]] > indexes[head]
                or datetime.fromisoformat(row["observed_at"]) > datetime.fromisoformat(payload["broker_snapshot_observed_at"])):
            raise ValueError("BOOK_B_CAPITAL_ACCOUNT_FUTURE_FLOW")
    accounting = payload.get("accounting")
    if accounting is not None:
        from .book_b_accounting import verify_observation
        report = verify_observation(root, accounting)
        if (report["ownership_head_sha256"] != head
                or report["capital_flow_head_sha256"] != payload.get("capital_flow_head_sha256")
                or report["broker_snapshot_sha256"] != payload.get("broker_snapshot_sha256")
                or report["observed_at"] != payload.get("broker_snapshot_observed_at")
                or number(report["cash"]) != number(payload["cash"])
                or number(report["liquidation_nav"]) != number(payload["settled_nav"])
                or number(report["risk_unit_factor"]) != number(state["capital_unit_factor"])):
            raise ValueError("BOOK_B_ACCOUNTING_ACCOUNT_MISMATCH")
        return number(report["conservative_risk_nav"])
    expected = (cash_by_head[head] + number(state["net_external_flow_total"])).quantize(Decimal(".01"))
    if expected != number(payload["cash"]).quantize(Decimal(".01")):
        raise ValueError("BOOK_B_CAPITAL_ACCOUNT_CASH_MISMATCH")
    return (number(payload["settled_nav"]) / number(state["capital_unit_factor"])).quantize(Decimal(".000001"))

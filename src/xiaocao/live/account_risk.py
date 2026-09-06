"""Pure Book B new-risk cap using the explicitly approved pilot loss budget.

10% drawdown halves new risk; 20% pauses new buys pending audited review.
These are loss budgets, not backtest optima or changes to the 8% position stop,
T+1, eligibility, allocation ceilings, or capital keys. No result authorizes
a trade or instructs a sale. This module performs no I/O.

Caller contract: in strict mode, prove coverage of validated inception-to-asof
settled history for ONE account, plus an optional reconciled current mark.
This pure function cannot prove coverage from the supplied rows alone. Paper
may explicitly use require_settled_history=False when no historical NAV curve
exists: a fresh reconciled mark starts tracking, with history_basis set to
since_activation. This is not a claim about lifetime maximum drawdown; never
fabricate historical settlements. The original seed remains a risk floor.
Live NAV must come
from the owned-lot lifecycle (settled_nav), never mixed broker assets or paper.
Paper NAV uses total_equity_after_exit_fee after ledger/valuation validation;
an intraday holdings snapshot alone is not settled evidence. Source digests
are provenance bindings, not authentication: validate the sources upstream.
load_latest_book_b_live_settlement only validates the latest file, so it must
not be presented as a validator for an entire historical directory.

Keep the original caller-supplied initial_capital (30000 for this pilot).
external_flow_total is cumulative ABSOLUTE deposits plus withdrawals since
inception, excluding that seed, not a net flow that can cancel to zero. Its
absence is unproved; any nonzero flow requires review, never a capital reset.
Persist and pass previous_receipt after every evaluation, including intraday
evaluations and blocks, to retain observed peaks and the 20% pause. There is
no automatic release/reset API. Strict mode still requires settled history;
paper epoch mode requires a fresh current mark on every call. Persist the
tracking_epoch_started_at in the receipt; blocked reads do not restart it.
Previous receipts must use the same history_basis; switching modes is not an
implicit migration or a way to reset the tracked peak/pause.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable
from zoneinfo import ZoneInfo


NAV_BASIS = "book_b_cash_plus_liquidation_after_exit_fee"
POLICY_ID = "book_b_pilot_drawdown_10_20_v1"
_CHINA = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class NavObservation:
    date: str
    nav: float
    account_id: str
    initial_capital: float
    external_flow_total: float
    nav_basis: str
    status: str  # history: settled; current_nav: reconciled
    observed_at: str  # timezone-aware ISO timestamp; settlement completion/mark
    evidence_digest: str  # SHA-256 of upstream validated source evidence


@dataclass(frozen=True)
class AccountRiskReceipt:
    account_id: str
    asof: str
    initial_capital: float | None
    expected_settlement_date: str
    nav: float | None
    nav_observed_at: str | None
    high_water_mark: float | None
    drawdown_pct: float | None  # percent units: 10.0 means 10%, not 0.10
    deploy_factor: float  # cap on NEW risk only; never increases other gates
    status: str  # NORMAL / REDUCED / PAUSED / BLOCKED
    reasons: tuple[str, ...]
    review_required: bool
    pause_latched: bool
    evidence_digest: str
    nav_basis: str = NAV_BASIS
    policy_id: str = POLICY_ID
    history_basis: str = "settled_history"
    tracking_epoch_started_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def _day(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("noncanonical date")
    return parsed


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def _number(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("number required")
    number = Decimal(str(value))
    if (not number.is_finite() or not math.isfinite(float(number))
            or (number != 0 and float(number) == 0)):
        raise ValueError("finite number required")
    return number


def _valid_digest(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def _canonical(value: Any) -> str:
    # Invalid evidence is hashed too, without emitting NaN in receipt JSON.
    def safe(item: Any) -> Any:
        if isinstance(item, (NavObservation, AccountRiskReceipt)):
            return safe(asdict(item))
        if isinstance(item, dict):
            return {str(key): safe(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [safe(val) for val in item]
        if isinstance(item, datetime):
            return item.isoformat()
        if isinstance(item, Decimal):
            return {"decimal": str(item)}
        if isinstance(item, float):
            return {"nonfinite_number": str(item)} if not math.isfinite(item) else item
        if item is None or isinstance(item, (str, int, bool)):
            return item
        return {"invalid_type": type(item).__name__}

    return json.dumps(safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def evaluate_account_risk(
    history: Iterable[NavObservation],
    *,
    current_nav: NavObservation | None = None,
    asof: datetime,
    account_id: str,
    initial_capital: float,
    expected_settlement_date: str | None = None,
    previous_receipt: AccountRiskReceipt | None = None,
    require_settled_history: bool = True,
) -> AccountRiskReceipt:
    """Return an immutable, JSON-safe cap; invalid evidence yields BLOCKED/0.

    asof is timezone-aware. expected_settlement_date is the exact latest
    completed settlement date required by the caller's trading calendar in
    strict mode, even when current_nav is supplied. Only paper:B may opt out
    explicitly; its fresh current_nav is mandatory and the expected date may
    be None. With no history its peak is max(initial_capital, current, prior
    peak), never a newly inferred principal. History timestamps must be post-close on
    their stated China date; current marks must be same-day and <=300s old.
    Identical duplicate observations are idempotent, conflicting dates block.
    Pass only a trusted previous receipt produced here, unchanged. A past 20%
    chronological drawdown or latched receipt cannot be undone by a rebound.
    """
    errors: set[str] = set()
    capital = peak = None
    now = expected = None
    paused = False
    previous_observed = None
    epoch_started = None
    epoch_mode = require_settled_history is False
    history_basis = "since_activation" if epoch_mode else "settled_history"
    if type(require_settled_history) is not bool:
        errors.add("HISTORY_REQUIREMENT_INVALID")
    if epoch_mode and account_id != "paper:B":
        errors.add("TRACKING_EPOCH_PAPER_ONLY")
    if epoch_mode and current_nav is None:
        errors.add("TRACKING_EPOCH_CURRENT_NAV_REQUIRED")
    rows: list[NavObservation] = []
    try:
        rows = list(history)
    except (TypeError, ValueError):
        errors.add("HISTORY_INVALID")
    try:
        capital = _number(initial_capital)
        if capital <= 0:
            raise ValueError
        peak = capital
    except (ValueError, OverflowError):
        capital = None
        errors.add("INITIAL_CAPITAL_INVALID")
    if account_id not in ("paper:B", "live:B"):
        errors.add("ACCOUNT_ID_INVALID")
    try:
        if not isinstance(asof, datetime):
            raise ValueError
        now = _time(asof.isoformat())
    except (ValueError, TypeError):
        errors.add("ASOF_INVALID")
    if not epoch_mode or expected_settlement_date is not None:
        try:
            expected = _day(expected_settlement_date)
            if now is not None and expected > now.astimezone(_CHINA).date():
                raise ValueError
        except (ValueError, TypeError):
            errors.add("EXPECTED_SETTLEMENT_DATE_INVALID")

    if previous_receipt is not None:
        try:
            prev = previous_receipt
            if (not isinstance(prev, AccountRiskReceipt)
                    or "PREVIOUS_RECEIPT_INVALID" in prev.reasons):
                # Repair the original receipt chain; a fresh mark cannot
                # establish which peak/pause was lost with an invalid anchor.
                raise ValueError
            if (prev.account_id != account_id or prev.nav_basis != NAV_BASIS
                    or prev.policy_id != POLICY_ID
                    or prev.history_basis != history_basis
                    or _number(prev.initial_capital) != capital):
                raise ValueError
            if now is None or _time(prev.asof) > now:
                raise ValueError
            if prev.history_basis not in ("settled_history", "since_activation"):
                raise ValueError
            if prev.tracking_epoch_started_at is not None:
                epoch_started = _time(prev.tracking_epoch_started_at)
                if account_id != "paper:B" or epoch_started > _time(prev.asof):
                    raise ValueError
            if prev.history_basis == "since_activation":
                if account_id != "paper:B" or (epoch_started is None and prev.status != "BLOCKED"):
                    raise ValueError
            factors = {"NORMAL": 1.0, "REDUCED": 0.5, "PAUSED": 0.0, "BLOCKED": 0.0}
            if (prev.status not in factors or prev.deploy_factor != factors[prev.status]
                    or type(prev.pause_latched) is not bool
                    or type(prev.review_required) is not bool
                    or not _valid_digest(prev.evidence_digest)):
                raise ValueError
            paused = prev.pause_latched or prev.status == "PAUSED"
            if (prev.review_required != (prev.status == "BLOCKED" or paused)
                    or (paused and prev.status not in ("PAUSED", "BLOCKED"))):
                raise ValueError
            if prev.high_water_mark is not None:
                prior_peak = _number(prev.high_water_mark)
                if capital is None or prior_peak < capital:
                    raise ValueError
                peak = prior_peak
            if prev.status != "BLOCKED":
                if (prev.high_water_mark is None or prev.nav_observed_at is None
                        or not 0 < _number(prev.nav) <= peak
                        or not 0 <= _number(prev.drawdown_pct) <= 100):
                    raise ValueError
            elif prev.nav is not None or prev.drawdown_pct is not None:
                raise ValueError
            if prev.nav_observed_at is not None:
                previous_observed = _time(prev.nav_observed_at)
                if previous_observed > _time(prev.asof):
                    raise ValueError
        except (ValueError, TypeError, AttributeError, OverflowError):
            errors.add("PREVIOUS_RECEIPT_INVALID")

    dated: dict[date, tuple[Decimal, datetime]] = {}
    current = None
    # Sorting all evidence before validation makes failures deterministic too.
    ordered = sorted(rows, key=_canonical)
    for row, is_current in [(row, False) for row in ordered] + (
        [(current_nav, True)] if current_nav is not None else []
    ):
        try:
            if not isinstance(row, NavObservation):
                raise ValueError("OBSERVATION_INVALID")
            if row.account_id != account_id:
                raise ValueError("ACCOUNT_ID_MISMATCH")
            if row.nav_basis != NAV_BASIS:
                raise ValueError("NAV_BASIS_MISMATCH")
            if _number(row.initial_capital) != capital:
                raise ValueError("INITIAL_CAPITAL_MISMATCH")
            if _number(row.external_flow_total) != 0:
                raise ValueError("EXTERNAL_FLOW_REVIEW_REQUIRED")
            nav = _number(row.nav)
            if nav <= 0:
                raise ValueError("NAV_INVALID")
            day = _day(row.date)
            observed = _time(row.observed_at)
            local = observed.astimezone(_CHINA)
            if now is None or observed > now or day > now.astimezone(_CHINA).date():
                raise ValueError("FUTURE_EVIDENCE")
            if local.date() != day:
                raise ValueError("OBSERVATION_DATE_MISMATCH")
            if not _valid_digest(row.evidence_digest):
                raise ValueError("SOURCE_DIGEST_INVALID")
            if is_current:
                if row.status != "reconciled":
                    raise ValueError("CURRENT_NAV_NOT_RECONCILED")
                if day != now.astimezone(_CHINA).date() or (now - observed).total_seconds() > 300:
                    raise ValueError("CURRENT_NAV_STALE")
                current = (day, nav, observed)
            else:
                if row.status != "settled" or local.hour < 15:
                    raise ValueError("HISTORY_NOT_SETTLED")
                if day in dated and dated[day][0] != nav:
                    raise ValueError("DUPLICATE_DATE_CONFLICT")
                dated[day] = (nav, max(observed, dated.get(day, (nav, observed))[1]))
        except (ValueError, TypeError, AttributeError, OverflowError) as exc:
            reason = str(exc)
            errors.add(reason if reason.isupper() else "OBSERVATION_INVALID")

    if not dated and not epoch_mode:
        errors.add("SETTLED_HISTORY_REQUIRED")
    elif dated and not epoch_mode and max(dated) != expected:
        errors.add("SETTLED_HISTORY_STALE_OR_UNEXPECTED")
    if current is not None and current[0] in dated and dated[current[0]][0] != current[1]:
        errors.add("DUPLICATE_DATE_CONFLICT")

    nav_out = drawdown = None
    observed_out = previous_observed
    if not errors:
        # Replay chronology from the original seed, NOT the previous peak:
        # a later peak must never retroactively create a historical breach.
        running_peak = capital
        for day in sorted(dated):
            value, observed = dated[day]
            if previous_observed is not None and observed >= previous_observed:
                running_peak = max(running_peak, peak)
            running_peak = max(running_peak, value)
            paused |= value * 100 <= running_peak * 80
        peak = max(peak, running_peak)
        _, nav_out, observed_out = current or (max(dated), *dated[max(dated)])
        if previous_observed is not None and observed_out < previous_observed:
            errors.add("NAV_OBSERVATION_REGRESSION")
            observed_out = previous_observed
        else:
            peak = max(peak, nav_out)
            paused |= nav_out * 100 <= peak * 80
            drawdown = (peak - nav_out) * 100 / peak
            if epoch_mode and epoch_started is None:
                epoch_started = now

    if errors:
        status, factor = "BLOCKED", 0.0
        nav_out = drawdown = None
        reasons = tuple(sorted(errors))
    elif paused:
        status, factor = "PAUSED", 0.0
        reasons = ("DRAWDOWN_20_PCT_REVIEW_REQUIRED",)
    elif nav_out * 100 <= peak * 90:
        status, factor = "REDUCED", 0.5
        reasons = ("DRAWDOWN_10_PCT_NEW_RISK_HALVED",)
    else:
        status, factor = "NORMAL", 1.0
        reasons = ("WITHIN_PILOT_LOSS_BUDGET",)

    digest = hashlib.sha256(_canonical({
        "policy_id": POLICY_ID, "nav_basis": NAV_BASIS,
        "history": sorted({_canonical(row) for row in rows}),
        "current_nav": current_nav, "asof": asof, "account_id": account_id,
        "initial_capital": initial_capital, "expected_settlement_date": expected_settlement_date,
        "previous_receipt": previous_receipt, "reasons": reasons,
        "require_settled_history": require_settled_history,
        "history_basis": history_basis,
        "tracking_epoch_started_at": epoch_started,
    }).encode("utf-8")).hexdigest()
    return AccountRiskReceipt(
        account_id=account_id if isinstance(account_id, str) else "",
        asof=now.isoformat() if now is not None else "",
        initial_capital=float(capital) if capital is not None else None,
        expected_settlement_date=expected.isoformat() if expected is not None else "",
        nav=float(nav_out) if nav_out is not None else None,
        nav_observed_at=observed_out.isoformat() if observed_out is not None else None,
        high_water_mark=float(peak) if peak is not None else None,
        drawdown_pct=float(drawdown) if drawdown is not None else None,
        deploy_factor=factor, status=status, reasons=reasons,
        review_required=bool(errors) or paused, pause_latched=paused,
        evidence_digest=digest,
        history_basis=history_basis,
        tracking_epoch_started_at=epoch_started.isoformat() if epoch_started is not None else None,
    )

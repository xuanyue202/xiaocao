"""Operating-contract invariants (docs/OPERATING_CONTRACT.md).

This slice covers the two-key capital-action safety boundary: the structural
guarantee that no real-capital order can be placed without BOTH keys, that an
agent cannot self-grant either, and that paper/sensor/research are never blocked.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from xiaocao.live import safety, status
from xiaocao.live.exit_policy import decide_sell_action
from xiaocao.live.safety import (
    CapitalActionDenied,
    authorize_capital_action,
    make_authorization,
    require_capital_action,
)

NOW = datetime(2026, 6, 20, 1, 30, tzinfo=timezone.utc)
KEY = "test-signing-key-not-in-automation-env"


def _valid_auth_file(tmp_path, *, max_notional=20000.0, sides=None, codes=None, hours=24):
    auth = make_authorization(
        scope="test", max_notional=max_notional, signing_key=KEY,
        sides=sides, codes=codes,
        expires_at=(NOW + timedelta(hours=hours)).isoformat(timespec="seconds"),
        issued_at=NOW.isoformat(timespec="seconds"),
    )
    path = tmp_path / "live_authorization.json"
    path.write_text(json.dumps(auth), encoding="utf-8")
    return path


def _both_keys_env():
    return {safety.ENV_LIVE_ENABLED: "true", safety.ENV_SIGNING_KEY: KEY}


@pytest.mark.parametrize("kind", ["paper", "sensor", "research", "simulation"])
def test_paper_sensor_research_always_allowed(tmp_path, kind):
    # No env, no authorization — must still be allowed (research never blocks).
    d = authorize_capital_action(
        kind=kind, side="BUY", code="000001.XSHG", notional=1e9,
        auth_path=tmp_path / "none.json", audit_path=tmp_path / "audit.jsonl", env={},
    )
    assert d.allowed and "always-allowed" in d.reason


def test_unknown_kind_denied_by_default(tmp_path):
    d = authorize_capital_action(
        kind="something_new", auth_path=tmp_path / "none.json",
        audit_path=tmp_path / "audit.jsonl", env=_both_keys_env(), now=NOW,
    )
    assert not d.allowed and "deny-by-default" in d.reason


def test_real_capital_denied_when_env_off(tmp_path):
    auth = _valid_auth_file(tmp_path)
    d = authorize_capital_action(
        kind="real_capital", side="BUY", code="000001.XSHG", notional=100.0,
        auth_path=auth, audit_path=tmp_path / "audit.jsonl",
        env={safety.ENV_SIGNING_KEY: KEY}, now=NOW,  # key 1 missing
    )
    assert not d.allowed and "key 1 missing" in d.reason


def test_real_capital_denied_when_no_auth_file(tmp_path):
    d = authorize_capital_action(
        kind="real_capital", notional=100.0,
        auth_path=tmp_path / "missing.json", audit_path=tmp_path / "audit.jsonl",
        env=_both_keys_env(), now=NOW,
    )
    assert not d.allowed and "key 2 missing" in d.reason and "no authorization file" in d.reason


def test_real_capital_denied_when_signing_key_absent(tmp_path):
    auth = _valid_auth_file(tmp_path)
    d = authorize_capital_action(
        kind="real_capital", notional=100.0, auth_path=auth,
        audit_path=tmp_path / "audit.jsonl",
        env={safety.ENV_LIVE_ENABLED: "true"}, now=NOW,  # no signing key in env
    )
    assert not d.allowed and "key 2 missing" in d.reason


def test_real_capital_denied_when_signature_tampered(tmp_path):
    # The agent cannot forge: editing scope/notional without the key breaks HMAC.
    auth = _valid_auth_file(tmp_path)
    obj = json.loads(auth.read_text())
    obj["max_notional"] = 10_000_000.0  # tamper to widen the limit
    auth.write_text(json.dumps(obj), encoding="utf-8")
    d = authorize_capital_action(
        kind="real_capital", notional=100.0, auth_path=auth,
        audit_path=tmp_path / "audit.jsonl", env=_both_keys_env(), now=NOW,
    )
    assert not d.allowed and "invalid signature" in d.reason


def test_real_capital_denied_when_expired(tmp_path):
    auth = _valid_auth_file(tmp_path, hours=1)
    later = NOW + timedelta(hours=2)
    d = authorize_capital_action(
        kind="real_capital", notional=100.0, auth_path=auth,
        audit_path=tmp_path / "audit.jsonl", env=_both_keys_env(), now=later,
    )
    assert not d.allowed and "expired" in d.reason


def test_real_capital_denied_when_over_notional(tmp_path):
    auth = _valid_auth_file(tmp_path, max_notional=5000.0)
    d = authorize_capital_action(
        kind="real_capital", notional=5000.01, auth_path=auth,
        audit_path=tmp_path / "audit.jsonl", env=_both_keys_env(), now=NOW,
    )
    assert not d.allowed and "exceeds authorized max" in d.reason


def test_real_capital_denied_when_side_or_code_out_of_scope(tmp_path):
    auth = _valid_auth_file(tmp_path, sides=["BUY"], codes=["000001.XSHG"])
    d_side = authorize_capital_action(
        kind="real_capital", side="SELL", code="000001.XSHG", notional=100.0,
        auth_path=auth, audit_path=tmp_path / "audit.jsonl", env=_both_keys_env(), now=NOW,
    )
    d_code = authorize_capital_action(
        kind="real_capital", side="BUY", code="600519.XSHG", notional=100.0,
        auth_path=auth, audit_path=tmp_path / "audit.jsonl", env=_both_keys_env(), now=NOW,
    )
    assert not d_side.allowed and "authorized scope" in d_side.reason
    assert not d_code.allowed and "authorized scope" in d_code.reason


def test_real_capital_allowed_with_both_keys_in_scope(tmp_path):
    auth = _valid_auth_file(tmp_path, max_notional=20000.0, sides=["BUY", "SELL"])
    audit = tmp_path / "audit.jsonl"
    d = authorize_capital_action(
        kind="real_capital", side="BUY", code="000001.XSHG", notional=15000.0,
        auth_path=auth, audit_path=audit, env=_both_keys_env(), now=NOW,
    )
    assert d.allowed and d.reason == "two-key authorized"
    rows = [json.loads(l) for l in audit.read_text().splitlines() if l.strip()]
    assert rows and rows[-1]["allowed"] is True and rows[-1]["kind"] == "real_capital"


def test_require_capital_action_raises_on_deny_returns_on_allow(tmp_path):
    auth = _valid_auth_file(tmp_path)
    audit = tmp_path / "audit.jsonl"
    with pytest.raises(CapitalActionDenied):
        require_capital_action(
            kind="real_capital", notional=100.0, auth_path=tmp_path / "missing.json",
            audit_path=audit, env=_both_keys_env(), now=NOW,
        )
    d = require_capital_action(
        kind="real_capital", side="BUY", notional=100.0, auth_path=auth,
        audit_path=audit, env=_both_keys_env(), now=NOW,
    )
    assert d.allowed


def test_every_decision_is_audited(tmp_path):
    audit = tmp_path / "audit.jsonl"
    authorize_capital_action(kind="paper", auth_path=tmp_path / "x.json", audit_path=audit, env={})
    authorize_capital_action(
        kind="real_capital", notional=1.0, auth_path=tmp_path / "x.json",
        audit_path=audit, env={}, now=NOW,
    )
    rows = [json.loads(l) for l in audit.read_text().splitlines() if l.strip()]
    assert len(rows) == 2
    assert rows[0]["allowed"] is True and rows[1]["allowed"] is False


# --------------------------------------------------------------------------- #
# §5 fill-model invariant: a paper fill never exceeds the basket abandon bound.
# --------------------------------------------------------------------------- #
def _paper_record():
    import sys
    from pathlib import Path
    scripts = Path(__file__).resolve().parents[1] / "kronos_screen" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import paper_record  # noqa: E402
    return paper_record


@pytest.mark.parametrize(
    "open_px,basket,window",
    [
        (10.0, 10.10, {"vwap": 10.20, "low": 10.00, "high": 10.30, "time": "0931"}),  # vwap>L, capped by L
        (10.0, 10.10, {"vwap": 9.90, "low": 9.85, "high": 10.05, "time": "0931"}),    # vwap<L
        (10.0, 10.02, {"vwap": 10.50, "low": 10.00, "high": 10.60, "time": "0931"}),  # basket is the binding cap
        (10.0, 10.10, None),                                                          # no window -> L fallback
    ],
)
def test_paper_fill_never_exceeds_basket_abandon_bound(open_px, basket, window):
    pr = _paper_record()
    record = {"open": open_px, "basket_price": basket, "basket_rule": "test"}
    price, basis, _, _ = pr._fill_price_from_window(record, window=window, limit_premium_pct=0.5)
    if price is not None:  # None == SKIP (limit not reached), which is allowed
        assert price <= basket + 1e-9, f"{basis}: fill {price} exceeded basket abandon bound {basket}"


def test_non_ascii_signature_denies_cleanly_and_audits(tmp_path):
    # A crafted non-ASCII signature must DENY (not crash hmac.compare_digest) and
    # still write an audit row; require_capital_action must raise CapitalActionDenied,
    # not a TypeError.
    auth = _valid_auth_file(tmp_path)
    obj = json.loads(auth.read_text())
    obj["signature"] = "café-not-a-real-sig"  # non-ASCII
    auth.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    d = authorize_capital_action(
        kind="real_capital", notional=100.0, auth_path=auth,
        audit_path=audit, env=_both_keys_env(), now=NOW,
    )
    assert not d.allowed and "invalid signature" in d.reason
    rows = [json.loads(l) for l in audit.read_text().splitlines() if l.strip()]
    assert rows and rows[-1]["allowed"] is False
    with pytest.raises(CapitalActionDenied):
        require_capital_action(kind="real_capital", notional=100.0, auth_path=auth,
                               audit_path=audit, env=_both_keys_env(), now=NOW)


def test_omitted_scoped_attributes_fail_closed(tmp_path):
    # An authorization that RESTRICTS an attribute must DENY when the action omits
    # it — an omitted notional/side/code must never bypass the scope.
    auth = _valid_auth_file(tmp_path, max_notional=5000.0, sides=["BUY"], codes=["000001.XSHG"])
    audit = tmp_path / "audit.jsonl"
    common = dict(kind="real_capital", auth_path=auth, audit_path=audit, env=_both_keys_env(), now=NOW)
    # notional omitted vs a max_notional cap
    assert not authorize_capital_action(**common, side="BUY", code="000001.XSHG").allowed
    # side omitted vs a sides allowlist
    assert not authorize_capital_action(**common, code="000001.XSHG", notional=100.0).allowed
    # code omitted vs a codes allowlist
    assert not authorize_capital_action(**common, side="BUY", notional=100.0).allowed


def test_real_capital_allow_fails_closed_when_audit_unwritable(tmp_path):
    # A real-capital ALLOW that cannot be durably audited must convert to a DENY.
    auth = _valid_auth_file(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")  # a file where a dir is needed
    d = authorize_capital_action(
        kind="real_capital", side="BUY", notional=100.0, auth_path=auth,
        audit_path=blocker / "audit.jsonl", env=_both_keys_env(), now=NOW,
    )
    assert not d.allowed and "audit write failed" in d.reason


def test_paper_fill_skips_when_window_low_above_limit():
    pr = _paper_record()
    # open=10 -> L=min(10*1.005, basket=10.10)=10.05; window low 10.06 never trades through L.
    record = {"open": 10.0, "basket_price": 10.10}
    price, basis, _, meta = pr._fill_price_from_window(
        record, window={"vwap": 10.10, "low": 10.06, "high": 10.20, "time": "0931"}, limit_premium_pct=0.5,
    )
    assert price is None and meta.get("skip_reason") == "LIMIT_NOT_REACHED"


def test_real_capital_denied_when_expires_at_is_naive_tz(tmp_path):
    # A hand-minted authorization with a NAIVE expiry (no tz offset) is ambiguous;
    # the gate must fail-closed, not silently relabel it UTC (which would widen the
    # real-capital window by the minter's local offset — a fail-OPEN on expiry).
    auth = make_authorization(
        scope="test", max_notional=20000.0, signing_key=KEY,
        expires_at="2027-01-01T15:00:00",  # naive: no +00:00
        issued_at=NOW.isoformat(timespec="seconds"),
    )
    path = tmp_path / "live_authorization.json"
    path.write_text(json.dumps(auth), encoding="utf-8")
    d = authorize_capital_action(
        kind="real_capital", side="BUY", notional=100.0, auth_path=path,
        audit_path=tmp_path / "audit.jsonl", env=_both_keys_env(), now=NOW,
    )
    assert not d.allowed and "expires_at" in d.reason


# --------------------------------------------------------------------------- #
# §11 invariant: book A/B fixture replay (the iteration-7 raison d'être —
# book A/B drift was once -4,191). Same picks through both口径; the realized
# spread must be ENTIRELY the exit-policy difference, with no bookkeeping drift.
# Book B's exit is the REAL production decision (exit_policy.decide_sell_action);
# book A always exits at next_close.
# --------------------------------------------------------------------------- #
def _book_b_exit(pick):
    """Replay the production staged-exit decision. HARD_STOP executes intraday at
    the checkpoint price; everything else holds to the 14:55 discipline pass and
    exits at the close-aligned 14:55 price — exactly the staging the live loop runs."""
    d = decide_sell_action(
        {}, detail={}, latest_price=pick["intraday_price"], peak=pick["peak"],
        dd_pct=pick["dd_pct"], dd_threshold=2.0, t1_blocked=False, hold_days=1,
        signal_score=0.5, hard_dd_threshold=8.0, now=pick["now"],
    )
    if d["triggered"] and d["sell_reason"] == "HARD_STOP":
        return pick["intraday_price"], "HARD_STOP"
    return pick["price_1455"], d.get("sell_reason")


def test_ab_replay_spread_is_entirely_exit_policy_no_drift(tmp_path):
    eod_t = datetime(2026, 6, 22, 14, 55)
    intraday_t = datetime(2026, 6, 22, 10, 0)
    picks = [
        # no stop fires -> book B exits at 14:55 == next_close -> books AGREE (zero drift)
        {"code": "AAA", "entry": 10.0, "shares": 1000, "next_close": 10.5,
         "intraday_price": 10.5, "price_1455": 10.5, "peak": 10.6, "dd_pct": 1.0, "now": eod_t},
        # hard stop fires intraday at 18.5 while next_close is 21.0 -> divergence
        {"code": "BBB", "entry": 20.0, "shares": 500, "next_close": 21.0,
         "intraday_price": 18.5, "price_1455": 21.0, "peak": 20.5, "dd_pct": 9.0, "now": intraday_t},
    ]
    book_a = book_b = attribution = 0.0
    reasons = {}
    for p in picks:
        exit_b, reason = _book_b_exit(p)
        reasons[p["code"]] = reason
        book_a += (p["next_close"] - p["entry"]) * p["shares"]
        book_b += (exit_b - p["entry"]) * p["shares"]
        attribution += (exit_b - p["next_close"]) * p["shares"]  # exit-policy difference only

    # the production exit policy: AAA defers to the 14:55 discipline, BBB hard-stops
    assert reasons["AAA"] == "EOD_DISCIPLINE_1455"
    assert reasons["BBB"] == "HARD_STOP"
    # the entire A/B spread is the exit difference — no entry/cost-basis/recon drift
    assert round(book_b - book_a, 6) == round(attribution, 6) == -1250.0

    # and the digest computes the SAME spread from the seeded book accounts
    (tmp_path / "paper_account.json").write_text(json.dumps({"realized_pnl": book_b}), encoding="utf-8")
    (tmp_path / "paper_account_A.json").write_text(json.dumps({"realized_pnl": book_a}), encoding="utf-8")
    digest = status.build_digest(live_dir=tmp_path, market_date="2026-06-22")
    assert digest["book_a_present"] is True
    assert digest["ab_realized_delta"] == round(book_b - book_a, 2) == -1250.0


def test_ab_replay_books_agree_when_no_stop_fires():
    # Identical inputs, no stop -> book B (14:55 == next_close) must equal book A.
    # A nonzero delta here would be a bookkeeping drift bug (the -4191 failure mode).
    p = {"code": "AAA", "entry": 10.0, "shares": 1000, "next_close": 10.5,
         "intraday_price": 10.5, "price_1455": 10.5, "peak": 10.55, "dd_pct": 1.0,
         "now": datetime(2026, 6, 22, 14, 55)}
    exit_b, reason = _book_b_exit(p)
    assert reason == "EOD_DISCIPLINE_1455"
    assert (p["next_close"] - p["entry"]) * p["shares"] == (exit_b - p["entry"]) * p["shares"]

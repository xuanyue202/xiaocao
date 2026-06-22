"""Drift guard for the parameter registry (src/xiaocao/strategy/params.py).

The registry is the SSOT for frozen strategy/risk thresholds. These tests fail
if any consumer's live value diverges from the registry — catching silent drift
and proving the registry is authoritative, not just documentation.
"""
from __future__ import annotations

import sys
from pathlib import Path

from xiaocao.strategy import params, rules
from xiaocao.live import exit_policy


def _kronos_scripts_on_path():
    p = Path(__file__).resolve().parents[1] / "kronos_screen" / "scripts"
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def test_rewired_consumers_match_registry():
    # rules.py and exit_policy.py now import these from the registry.
    assert (rules.SUPER_JW, rules.STRONG_JW, rules.QUALIFIED_JW) == (
        params.SUPER_JW, params.STRONG_JW, params.QUALIFIED_JW)
    assert rules.DIRECTION_DISCOUNT == params.DIRECTION_DISCOUNT
    assert exit_policy.PROFILE_DD is params.PROFILE_DD
    assert exit_policy.PROFILE_HARD_DD is params.PROFILE_HARD_DD


def test_direction_discount_is_wired_not_a_hardcoded_literal():
    # Regression for the registry-phantom bug: DIRECTION_DISCOUNT used to be a
    # registry knob that rules.py ignored (11 hardcoded `1.3`), so editing the
    # registry changed nothing while the SSOT/ledger/digest reported the new value
    # — a "真的谎言". rules.py must drive the discount from the registry symbol.
    src = (Path(__file__).resolve().parents[1] / "src" / "xiaocao" / "strategy" / "rules.py").read_text()
    assert "DIRECTION_DISCOUNT" in src
    assert "/ 1.3" not in src and "* 1.3" not in src, "direction discount must not be a hardcoded literal"


def test_documented_consumers_have_not_drifted():
    _kronos_scripts_on_path()
    import quality_governor  # noqa: E402
    import paper_record  # noqa: E402

    assert quality_governor.PRIMARY_THRESHOLD == params.PRIMARY_THRESHOLD
    assert paper_record.DEFAULT_DEPLOY_RATIO == params.DEPLOY_RATIO
    assert paper_record.DEFAULT_MAX_TOTAL_EXPOSURE_RATIO == params.MAX_TOTAL_EXPOSURE_RATIO
    assert paper_record.DEFAULT_FEE_RATE == params.FEE_RATE


def test_values_are_unchanged_from_validated_baseline():
    # Pin the validated values so a future edit to the registry is a conscious act.
    assert params.SUPER_JW == 300 and params.STRONG_JW == 200 and params.QUALIFIED_JW == 150
    assert params.DIRECTION_DISCOUNT == 1.3
    assert params.PROFILE_DD == {"v5": 2.0, "v6": 0.5}
    assert params.PROFILE_HARD_DD == {"v5": 8.0, "v6": 8.0}
    assert params.DEPLOY_RATIO == 0.5 and params.MAX_TOTAL_EXPOSURE_RATIO == 0.67


def test_all_params_frozen_until_a_pass_verdict():
    # Nothing is tunable-by-default; only the research harness may flip a param
    # after a PASS verdict. A non-frozen entry here is a mistake.
    assert all(p.frozen for p in params.REGISTRY.values())


def test_helpers():
    assert params.get("SUPER_JW") == 300
    assert params.as_dict()["QUALIFIED_JW"] == 150


def test_book_t_params_are_proposed_not_validated():
    # Book T params are the *candidate* tier: frozen, disjoint from the validated
    # REGISTRY, and consumed by nothing. They must NOT leak into the live SSOT
    # (REGISTRY / as_dict) until a trend_guards OOS PASS + §10 gate promotes them —
    # the param-layer mirror of the candidate↔verdict hypothesis discipline.
    assert set(params.BOOK_T_PROPOSED) & set(params.REGISTRY) == set()
    assert all(p.frozen for p in params.BOOK_T_PROPOSED.values())
    assert not (set(params.BOOK_T_PROPOSED) & set(params.as_dict()))

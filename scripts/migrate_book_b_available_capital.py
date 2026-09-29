"""One-time operator-approved APP capital migration; never scheduled minting.

Reuses the existing Keychain keys and signed scope/expiry. Does no trade,
cancel, unlock retry, source preparation, paper write or historical rewrite.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.book_b_capital import POLICY, digest, has_open_buy, policy
from xiaocao.live.book_b_live_lifecycle import project_book_b_live_account, _write_json_atomic
from xiaocao.live.capital_keychain import KeychainCapitalRuntime
from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight
from xiaocao.live.safety import DEFAULT_AUTH_PATH, ENV_SIGNING_KEY, load_authorization, sign_payload
from xiaocao.live.trading_execution import account_writer_lock
from xiaocao.live.trading_runner import build_foundersc_native_execution


def migrate(root: Path, *, snapshot: dict, env: dict, approval: str, apply: bool,
            now: datetime, auth_path: Path) -> dict:
    state = root / "output/live/book_b_live_execution"
    auth, reason = load_authorization(auth_path=auth_path, env=env, now=now)
    if auth is None:
        raise ValueError("CAPITAL_MIGRATION_EXISTING_AUTH_UNPROVEN:" + reason)
    with account_writer_lock(state / "account_writer_locks", "primary"):
        if has_open_buy(state):
            raise ValueError("CAPITAL_MIGRATION_OPEN_BUY_RECONCILE_REQUIRED")
        account = project_book_b_live_account(state, snapshot,
            trade_date=now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            now=now, sync_capital=False)
        binding = snapshot["fund_account_binding_sha256"]
        old_sha = digest(auth)
        existing = policy(state)
        if existing and existing["fund_account_binding_sha256"] != binding:
            raise ValueError("CAPITAL_MIGRATION_ACCOUNT_MISMATCH")
        grant = dict(auth)
        grant.update(capital_policy_id=POLICY, fund_account_binding_sha256=binding)
        grant["signature"] = sign_payload(grant, env[ENV_SIGNING_KEY])
        cfg = {"policy_id": POLICY, "logical_account_id": "primary",
            "fund_account_binding_sha256": binding, "approved_at": now.isoformat(),
            "approval_reference": approval, "previous_authorization_sha256": old_sha,
            "authorization_sha256": digest(grant)}
        cfg["policy_sha256"] = digest(cfg)
        if apply:
            if not approval.strip():
                raise ValueError("CAPITAL_MIGRATION_EXPLICIT_APPROVAL_REQUIRED")
            backup = state / "capital_migrations" / f"authorization-{old_sha}.json"
            if not backup.exists():
                _write_json_atomic(backup, auth)
            _write_json_atomic(auth_path, grant)
            if existing is None:
                _write_json_atomic(state / "capital_policy.json", cfg)
            verified, _ = load_authorization(auth_path=auth_path, env=env, now=now)
            if verified != grant:
                raise ValueError("CAPITAL_MIGRATION_SIGNED_READBACK_FAILED")
            account = project_book_b_live_account(state, snapshot,
                trade_date=account.trade_date, now=now)
        result = {"status": "applied" if apply else "preview",
            "capital_policy_id": POLICY, "available_cash": snapshot["funds_summary"]["available_cash"],
            "strategy_cash": account.cash, "strategy_nav": account.settled_nav,
            "owned_exposure": account.current_open_exposure,
            "owned_lot_count": len(account.lots), "capital_flow_head_sha256": account.capital_flow_head_sha256,
            "net_external_flow_total": account.net_external_flow_total,
            "unit_factor": account.capital_unit_factor,
            "authorization_sha256": digest(grant), "expiry_preserved": grant["expires_at"] == auth["expires_at"],
            "scope_preserved": all(grant.get(k) == auth.get(k) for k in ("scope", "sides", "codes")),
            "broker_snapshot_sha256": snapshot["snapshot_sha256"], "observed_at": snapshot["observed_at"]}
        if not apply:
            result.update(projected_strategy_cash=snapshot["funds_summary"]["available_cash"],
                projected_strategy_nav=round(snapshot["funds_summary"]["available_cash"] + account.liquidation_value_after_fee, 2))
        if apply:
            path = state / "capital_migrations" / f"{digest(result)}.json"
            _write_json_atomic(path, {**result, "account": account.as_dict(), "snapshot": snapshot})
            result["receipt_path"] = str(path)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approval-reference", default="")
    args = parser.parse_args()
    runtime = KeychainCapitalRuntime()
    env = runtime.safety_env()
    fingerprint = FounderscKeychainPreflight().trade_account_fingerprint()
    if not fingerprint:
        raise SystemExit("CAPITAL_MIGRATION_ACCOUNT_UNPROVEN")
    state = ROOT / "output/live/book_b_live_execution"
    _, broker = build_foundersc_native_execution(state,
        expected_fund_account_fingerprint=fingerprint, safety_env_provider=runtime.safety_env)
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    with account_writer_lock(state / "account_writer_locks", "primary"):
        snapshot = broker.read_live_account_snapshot(trade_date=day,
            expected_fund_account_fingerprint=fingerprint)
        result = migrate(ROOT, snapshot=snapshot, env=env,
            approval=args.approval_reference, apply=args.apply,
            now=datetime.now(timezone.utc), auth_path=ROOT / DEFAULT_AUTH_PATH)
    env.clear()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

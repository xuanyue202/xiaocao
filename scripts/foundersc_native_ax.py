#!/usr/bin/env python3
"""Build, probe, and explicitly unlock the Founder native AX helper."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight  # noqa: E402
from xiaocao.live.foundersc_native_ax import (  # noqa: E402
    FounderscNativeAXClient,
    FounderscNativeAXError,
    build_helper,
    expected_helper_path,
    native_runtime_ready,
    remote_bootstrap_guidance,
    source_digest,
)


RUNTIME_SOURCE_PATHS = (
    "native/foundersc_ax_executor",
    "src/xiaocao/live/foundersc_native_ax.py",
    "src/xiaocao/live/foundersc_native_broker.py",
    "src/xiaocao/live/foundersc_keychain.py",
    "src/xiaocao/live/trading_runner.py",
    "scripts/foundersc_native_ax.py",
    "scripts/book_b_live_morning.py",
    "scripts/configure_foundersc_trade_keychain.py",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=12.0)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--force", action="store_true")

    subparsers.add_parser("version")

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--build", action="store_true")
    preflight.add_argument("--table-audit", action="store_true")

    remote_bootstrap = subparsers.add_parser(
        "remote-bootstrap",
        help="build, probe, and emit one credential-free remote next action",
    )
    remote_bootstrap.add_argument("--table-audit", action="store_true")

    probe = subparsers.add_parser("probe")
    probe.add_argument("--table-audit", action="store_true")

    subparsers.add_parser("focus-unlock")

    fill_login = subparsers.add_parser("fill-login-keychain")
    fill_login.add_argument(
        "--acknowledge-local-password-fill",
        action="store_true",
        help=(
            "Explicitly allow one Keychain-backed client password fill; "
            "focuses CAPTCHA and never presses login"
        ),
    )

    unlock = subparsers.add_parser("unlock-keychain")
    unlock.add_argument(
        "--acknowledge-local-passguard-input",
        action="store_true",
        help=(
            "Explicitly allow one Keychain-backed password injection and one "
            "unlock confirmation; never submits an order"
        ),
    )
    return parser


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _git_readback() -> dict[str, object]:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )

    try:
        sha_result = run("rev-parse", "--verify", "HEAD")
        all_status = run("status", "--porcelain", "--untracked-files=normal")
        source_status = run(
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *RUNTIME_SOURCE_PATHS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "status": "unavailable",
            "sha": "",
            "worktree_clean": False,
            "runtime_source_clean": False,
        }
    sha = sha_result.stdout.strip()
    valid_sha = sha_result.returncode == 0 and len(sha) == 40
    return {
        "status": "readable" if valid_sha else "unavailable",
        "sha": sha if valid_sha else "",
        "worktree_clean": all_status.returncode == 0 and not all_status.stdout,
        "runtime_source_clean": (
            source_status.returncode == 0 and not source_status.stdout
        ),
    }


def _read_keychain_metadata(
    probe: dict[str, object],
    *,
    timeout_seconds: float,
) -> dict[str, object]:
    if probe.get("screen_locked") or probe.get("status") == (
        "screen_lock_state_unavailable"
    ):
        return {
            "status": "not_checked_machine_login_unavailable",
            "reason": "Keychain metadata check deferred until macOS login is unlocked",
        }
    return FounderscKeychainPreflight(timeout_seconds=timeout_seconds).run(
        read_secrets=False
    )


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "build":
            _emit(build_helper(root=ROOT, force=args.force))
            return 0
        if args.command in {"preflight", "remote-bootstrap"}:
            build_receipt = None
            if args.command == "remote-bootstrap" or args.build:
                build_receipt = build_helper(root=ROOT)
            helper = expected_helper_path(ROOT)
            client = FounderscNativeAXClient(
                helper_path=helper,
                root=ROOT,
                timeout_seconds=args.timeout_seconds,
            )
            probe = client.probe(table_audit=args.table_audit).as_dict()
            keychain = _read_keychain_metadata(
                probe,
                timeout_seconds=args.timeout_seconds,
            )
            runtime_ready = native_runtime_ready(probe)
            capabilities = probe.get("capabilities") or {}
            keychain_unlock_candidate = bool(
                isinstance(capabilities, dict)
                and capabilities.get("keychain_unlock_candidate")
                and keychain.get("trade_item_present")
                and keychain.get("trade_account_present")
            )
            keychain_login_fill_candidate = bool(
                isinstance(capabilities, dict)
                and capabilities.get("keychain_client_login_fill_candidate")
                and keychain.get("trade_item_present")
                and keychain.get("trade_account_present")
            )
            payload: dict[str, object] = {
                "status": "ready" if runtime_ready else "blocked",
                "build": build_receipt,
                "helper_path": str(helper),
                "source_digest": source_digest(ROOT),
                "native_runtime_ready": runtime_ready,
                "keychain_unlock_candidate": keychain_unlock_candidate,
                "keychain_login_fill_candidate": keychain_login_fill_candidate,
                "native": probe,
                "keychain": keychain,
            }
            if args.command == "remote-bootstrap":
                git = _git_readback()
                guidance = remote_bootstrap_guidance(probe, keychain)
                if not git.get("runtime_source_clean"):
                    guidance = {
                        **guidance,
                        "status": "blocked",
                        "next_action": "review_runtime_source_changes",
                        "actor": "human",
                        "commands": [],
                        "rerun_bootstrap_after_action": True,
                    }
                payload = {
                    **payload,
                    "status": guidance["status"],
                    "purpose": "foundersc_native_ax_remote_bootstrap",
                    "git": git,
                    "guidance": guidance,
                    "agent_contract": {
                        "bootstrap_mutates_broker_ui": False,
                        "keychain_secrets_read": False,
                        "captcha_is_slow_recovery_only": True,
                        "native_broker_probe_still_required": True,
                        "opencli_used_by_native_route": False,
                        "unknown_result_auto_retry_allowed": False,
                    },
                }
            _emit(payload)
            return 0
        client = FounderscNativeAXClient(
            helper_path=expected_helper_path(ROOT),
            root=ROOT,
            timeout_seconds=args.timeout_seconds,
        )
        if args.command == "version":
            receipt = client.version()
        elif args.command == "probe":
            receipt = client.probe(table_audit=args.table_audit)
        elif args.command == "focus-unlock":
            receipt = client.focus_unlock()
        elif args.command == "fill-login-keychain":
            receipt = client.fill_client_login_from_keychain(
                explicitly_enabled=args.acknowledge_local_password_fill,
                keychain_timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "unlock-keychain":
            receipt = client.unlock_from_keychain(
                explicitly_enabled=args.acknowledge_local_passguard_input,
                keychain_timeout_seconds=args.timeout_seconds,
            )
        else:  # pragma: no cover - argparse owns this boundary
            raise FounderscNativeAXError("NATIVE_AX_UNKNOWN_COMMAND")
        _emit(receipt.as_dict())
        if args.command == "focus-unlock":
            return 0 if receipt.status == "input_focused" else 2
        if args.command == "fill-login-keychain":
            return 0 if receipt.status == "client_login_password_filled" else 3
        if args.command == "unlock-keychain":
            return 0 if receipt.status == "unlocked" else 3
        return 0
    except FounderscNativeAXError as exc:
        _emit({"status": "blocked", "reason": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

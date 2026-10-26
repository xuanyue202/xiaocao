"""Human-owned WeChat playback; the agent observes only downloader evidence."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
import os
import select
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qs, urlencode, urlsplit

from .enrichment_types import EnrichmentError, EnrichmentDiagnosticError


def _claim_json(path: Path, value: dict) -> None:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
        json.dump(value, handle)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def human_playback_enabled(config_path: Path) -> bool:
    try:
        config = json.loads(config_path.read_text())
    except FileNotFoundError:
        return False
    except (OSError, ValueError) as exc:
        raise EnrichmentDiagnosticError("human playback configuration unreadable", category="input_error", code="native_entry_configuration_unreadable", stage="native_playback_input") from exc
    if not isinstance(config, dict):
        raise EnrichmentDiagnosticError("human playback configuration unreadable", category="input_error", code="native_entry_configuration_unreadable", stage="native_playback_input")
    from .native_entry import native_entry_held
    native_entry_held(config_path)  # Validate the legacy hold without clearing it.
    mode = config.get("playback_operator", "agent")
    if mode not in {"agent", "human"}:
        raise EnrichmentError("invalid playback operator")
    return mode == "human"


def next_human_poll(now: datetime, attempt: int) -> datetime:
    if now.tzinfo is None or type(attempt) is not int or attempt < 0:
        raise EnrichmentError("invalid human playback poll state")
    return now + timedelta(seconds=min(300, 10 * 2 ** min(attempt, 5)))


def notify_human_once(path: Path, *, published_at: str) -> None:
    """Claim before submitting a local notification; never send a relay message."""
    try:
        _claim_json(path, {"state": "submission_claimed"})
    except FileExistsError:
        return
    title = "小草课程：需要你操作"
    body = f"{published_at} 的草料入口已唤起。请手动打开、允许并播放；后台正在监听。"
    state = "unsupported_platform"
    if sys.platform == "darwin":
        script = ('on run argv\n display notification (item 2 of argv) '
                  'with title (item 1 of argv) sound name "Glass"\nend run')
        try:
            result = subprocess.run(["/usr/bin/osascript", "-e", script, title, body],
                                    capture_output=True, timeout=5)
            state = "submitted" if result.returncode == 0 else "submission_failed"
        except (OSError, subprocess.SubprocessError):
            state = "submission_unverified"
    path.write_text(json.dumps({"state": state, "display_verified": False}) + "\n")


def enable_capture_listener_pac() -> None:
    """Enable the existing capture PAC, preserving any unrelated active proxy."""
    from urllib.request import urlopen
    from xiaocao.yangsheng import network
    before = network.snapshot()
    current = network.fields(before["pac"])
    owned = "http://127.0.0.1:2023/proxy.pac"
    if current == {"URL": owned, "Enabled": "Yes"}:
        return
    if any("Enabled: No" not in value for value in before.values()):
        raise EnrichmentError("existing active proxy preserved")
    with urlopen(owned, timeout=3) as response:
        body = response.read(1024 * 1024).decode()
    if not all(value in body for value in ("FindProxyForURL", "DIRECT", "2023")):
        raise EnrichmentError("capture PAC unavailable")
    network.command("-setautoproxyurl", "Wi-Fi", owned)
    network.command("-setautoproxystate", "Wi-Fi", "on")
    if network.fields(network.command("-getautoproxyurl", "Wi-Fi")) != {"URL": owned, "Enabled": "Yes"}:
        raise EnrichmentError("capture PAC readback failed")


@contextmanager
def human_capture_network_owner(config_path: Path):
    """Restore capture-owned PAC on runner exit, including a lost parent pipe."""
    if not human_playback_enabled(config_path):
        yield
        return
    from xiaocao.yangsheng import network
    # The child inherits this flock, so a dying parent cannot hand ownership to
    # another runner until its restoration guardian has finished.
    lease_path = config_path.parent / "human-network-owner.lock"
    with lease_path.open("a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EnrichmentError("human capture network owner busy; original runner preserved") from None
        before = network.snapshot()
        owned = "http://127.0.0.1:2023/proxy.pac"
        guard = subprocess.Popen(
            [sys.executable, "-m", "xiaocao.yangsheng.network", "--wait-for-owner",
             "--receipt", str(config_path.parent / "human-network-restoration.json")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            start_new_session=True, pass_fds=(lease.fileno(),),
        )
        try:
            guard.stdin.write(json.dumps({"before": before, "owned_url": owned}) + "\n")
            guard.stdin.flush()
            ready, _, _ = select.select([guard.stdout], [], [], 10)
            if not ready or guard.stdout.readline().strip() != "armed":
                raise EnrichmentError("human capture network guard unavailable")
            yield
        finally:
            guard.stdin.close()
            try:
                guard.wait(timeout=15)
            finally:
                proof = network.restore(before, owned)
                if not proof.get("restored") and not proof.get("foreign_configuration_preserved"):
                    raise EnrichmentError("human capture proxy restoration unverified")


def launch_verified_caoliao(*, config_path: Path, item: dict, proof_path: Path,
                            receipt_path: Path, now: datetime) -> dict:
    """One merchant-issued entry; no screenshot, AX, click or hidden WeChat API."""
    import requests
    if not human_playback_enabled(config_path):
        raise EnrichmentError("human playback mode not enabled")
    config = json.loads(config_path.read_text())
    proof = json.loads(proof_path.read_text())
    target = f"#小程序://{item['mini_program_name']}/{item['mini_program_token']}"
    observed = datetime.fromisoformat(proof["observed_at"])
    if (observed.tzinfo is None or not 0 <= (now - observed).total_seconds() < 180
        or proof.get("identity") != item["identity"]
        or proof.get("capture_job_id") != item["capture_job_id"]
        or proof.get("saved_target") != target or proof.get("component_reopened") is not True
        or proof.get("editor_url") != config.get("editor_url")
        or config.get("last_configured_subscription_id") != item["identity"]
        or config.get("last_configured_message_sha256") != item["message_sha256"]):
        raise EnrichmentError("human playback saved target unverified")
    claim = {"identity": item["identity"], "capture_job_id": item["capture_job_id"],
             "target_sha256": hashlib.sha256(target.encode()).hexdigest(),
             "armed_at": now.isoformat(), "entry_launched": False}
    try:
        _claim_json(receipt_path, claim)
    except FileExistsError as exc:
        raise EnrichmentError("human entry already claimed; reconcile without relaunch") from exc
    try:
        response = requests.post("https://nc.caoliao.net/api/weixin/getWxUrlScheme", data={
            "query": urlencode({"q": config["public_url"], "trigger": "h5_wx_block"}),
            "path": config["provider_path"], "appid": config["provider_app_id"],
            "org_coding": config["provider_org_coding"],
        }, timeout=20)
        response.raise_for_status()
        data = response.json()["data"]["wx_url_scheme"]
        if isinstance(data, str):
            data = json.loads(data)
        page = urlsplit(data["appPath"])
        query = parse_qs(page.query)
        fetch = urlsplit(data["fetchUrl"])
        if (data.get("appId") != config["provider_app_id"] or page.path != config["provider_path"]
            or query.get("q") != [config["public_url"]] or query.get("trigger") != ["h5_wx_block"]
            or query.get("f") != ["schema"] or fetch.scheme != "https"
            or fetch.hostname != "wxurlgenerator.cli.im" or fetch.port not in {None, 443}
            or fetch.username or fetch.password):
            raise EnrichmentError("merchant human entry identity invalid")
        response = requests.get(data["fetchUrl"], timeout=20)
        response.raise_for_status()
        scheme = response.json()["data"]["urlScheme"]
        entry = urlsplit(scheme)
        if entry.scheme != "weixin" or entry.netloc != "dl" or entry.path != "/business/":
            raise EnrichmentError("merchant human entry invalid")
        subprocess.run(["/usr/bin/open", scheme], check=True, capture_output=True, timeout=10)
    except EnrichmentError:
        raise
    except (requests.RequestException, OSError, ValueError, KeyError, TypeError,
            subprocess.SubprocessError):
        raise EnrichmentError("human entry dispatch unresolved; reconcile the retained claim") from None
    claim.update(entry_launched=True, entry_sha256=hashlib.sha256(scheme.encode()).hexdigest())
    receipt_path.write_text(json.dumps(claim) + "\n")
    return claim

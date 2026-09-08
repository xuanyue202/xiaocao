import json

import pytest
from types import SimpleNamespace

from scripts.kol_daily import _lv_pdf_dependency_progress
from scripts import kol_daily
from xiaocao.kol.daily import DailyError


def fixture(tmp_path, status="waiting_cloud_transfer_receipt"):
    candidate = dict(identity="provider", version_key="provider-version", path="/v.mp4",
                     name="v.mp4", size=100, modified_at=10)
    request = {"episode_relationship_contract": {"candidates": [candidate]}}
    bundle = tmp_path / "validated_bundle.json"
    bundle.write_text(json.dumps({"items": [{"episode_relationship": {
        "primary_source_status": "pending", "related_source_part": {
            "identity": "provider", "version_key": "provider-version"}}}]}))
    item = {**candidate, "identity": "processed", "version_key": "processed-version",
            "provider_identity_sha256": "provider"}
    (tmp_path / "manifest.json").write_text(json.dumps({"items": {"processed": item}}))
    (tmp_path / "claims").mkdir()
    claim = {"source_identity": "processed", "source_version_key": "processed-version",
             "status": status, "stage": "cloud_transfer_confirmation",
             "next_poll_not_before": "2026-09-08T17:32:46+08:00",
             "reconciliation_status": "exact_private_copy_absent_after_bounded_retry"}
    claim_path = tmp_path / "claims/lv_transfer_processed-version.json"
    claim_path.write_text(json.dumps(claim))
    return request, bundle, claim_path


def test_pdf_wait_uses_real_primary_deadline_not_a_new_hour(tmp_path):
    request, bundle, _ = fixture(tmp_path)
    result = _lv_pdf_dependency_progress(request, bundle, tmp_path, [])
    assert result["next_poll_not_before"] == "2026-09-08T17:32:46+08:00"
    assert result["primary_source_identity"] == "processed"
    assert result["requires_relationship_review"] is False


def test_pdf_pending_bundle_is_invalidated_when_primary_is_blocked(tmp_path):
    request, bundle, _ = fixture(tmp_path, "blocked")
    result = _lv_pdf_dependency_progress(request, bundle, tmp_path, [])
    assert result["requires_relationship_review"] is True
    assert result["primary_source_status"] == "unavailable"
    assert result["primary_source_failure"]["receipt_reconciled"] is True
    assert "next_poll_not_before" not in result


def test_pdf_does_not_bind_a_different_video_version(tmp_path):
    request, bundle, claim_path = fixture(tmp_path)
    claim = json.loads(claim_path.read_text())
    claim["source_version_key"] = "different"
    claim_path.write_text(json.dumps(claim))
    with pytest.raises(DailyError, match="primary source claim binding"):
        _lv_pdf_dependency_progress(request, bundle, tmp_path, [])


def test_complete_primary_invalidates_pending_semantics(tmp_path):
    request, bundle, _ = fixture(tmp_path)
    transcript = {"identity": "processed", "version_key": "processed-version"}
    result = _lv_pdf_dependency_progress(request, bundle, tmp_path, [transcript])
    assert result["primary_source_status"] == "complete"
    assert result["requires_relationship_review"] is True


def test_runtime_requests_relationship_review_instead_of_reusing_pending_bundle(tmp_path, monkeypatch):
    request, bundle, _ = fixture(tmp_path, "blocked")
    request.update({"artifact_dir": str(tmp_path), "request_path": str(tmp_path / "request.json")})
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("PDF source")
    import hashlib
    request.update(evidence_path=str(evidence), evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())
    (tmp_path / "request.json").write_text(json.dumps(request))
    pdf = {"identity": "pdf", "version_key": "pdf-version", "media_type": "pdf",
           "name": "summary.pdf", "stage": "downloaded", "modified_at": 20}
    runtime = kol_daily.DailyRuntime.__new__(kol_daily.DailyRuntime)
    runtime.args = SimpleNamespace(video_output_dir=tmp_path, lv_session="lv", opencli_profile=None)
    runtime._lv_service = SimpleNamespace(
        pending_items=lambda: [pdf], download_opencli=lambda *a, **kw: None,
        ingest_browser_download=lambda *a: pdf, prepare_analysis_request=lambda *a: request,
        record_pdf_relationship=lambda *a, **kw: pytest.fail("stale bundle must not be routed"),
    )
    runtime._lv_listing = {}
    runtime._lv_listing_error = None
    runtime._ensure_lv_listing = lambda: None
    runtime._complete_lv_video_transcripts = lambda: []
    def receive(value, field):
        assert field == "bundle_path"
        assert value["primary_source_readback"]["primary_source_status"] == "unavailable"
        raise kol_daily.SemanticInputUnavailable(value, field)
    monkeypatch.setattr(kol_daily, "_read_agent_path", receive)
    result = runtime.lv(only_identity="pdf", refresh_listing=False)
    assert result["waiting_count"] == 1

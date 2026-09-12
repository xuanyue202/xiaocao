"""Byte integrity is independent of the review prose and local file layout."""
import hashlib

import pytest

from xiaocao.kol.initial_import import _legacy_transcript
from xiaocao.kol.publication import PublicationError


@pytest.mark.parametrize("mutation", [None, "character_count", "changed_bytes", "invalid_hash"])
def test_reviewed_utf8_evidence_binds_exact_bytes(tmp_path, mutation):
    raw = "中文证据\n".encode("utf-8")
    evidence = tmp_path / "evidence.txt"
    evidence.write_bytes(raw)
    entry = {"path": "evidence.txt", "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
    if mutation == "character_count":
        entry["size"] = len(raw.decode())
    elif mutation == "changed_bytes":
        evidence.write_bytes(raw + b"changed")
    elif mutation == "invalid_hash":
        entry["sha256"] = "bad"
    args = (tmp_path, tmp_path / "review.json", {"evidence": [entry]})
    if mutation is None:
        assert _legacy_transcript(*args) == (entry["sha256"], len(raw))
    else:
        with pytest.raises(PublicationError, match="reviewed evidence"):
            _legacy_transcript(*args)


def test_unavailable_source_requires_usable_portable_evidence_metadata(tmp_path):
    value = {"evidence": [{"path": "absent.txt", "sha256": "a" * 64, "size": 42}]}
    assert _legacy_transcript(tmp_path, tmp_path / "review.json", value) == ("a" * 64, 42)
    value["evidence"][0]["size"] = "42"
    with pytest.raises(PublicationError, match="source evidence is missing"):
        _legacy_transcript(tmp_path, tmp_path / "review.json", value)

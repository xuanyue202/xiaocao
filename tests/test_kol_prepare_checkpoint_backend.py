import json
from pathlib import Path

import pytest

from scripts import kol_prepare_checkpoint_backend as prepare


PREVIOUS=json.loads(
    (
        Path(__file__).parents[1]
        / "scripts/kol_backend_patches/additive_previous_sha256.json"
    ).read_text()
)


@pytest.mark.parametrize(
    ("source", "previous_sha"),
    [
        ("replay_cache.go", PREVIOUS["replay_cache.go"][0]),
        ("replay_cache.go", PREVIOUS["replay_cache.go"][1]),
        ("replay_cache_test.go", PREVIOUS["replay_cache_test.go"][0]),
        ("replay_cache_test.go", PREVIOUS["replay_cache_test.go"][1]),
    ],
)
def test_known_maintained_additive_source_upgrades_with_backup(
    tmp_path, monkeypatch, source, previous_sha,
):
    backend=tmp_path/"backend";resources=tmp_path/"resources"
    target=backend/source;desired=resources/source
    target.parent.mkdir(parents=True);desired.parent.mkdir(parents=True)
    target.write_bytes(b"known previous");desired.write_bytes(b"reviewed current")
    actual_sha=prepare.sha
    monkeypatch.setattr(prepare,"sha",lambda path:(
        previous_sha if path.read_bytes()==b"known previous" else actual_sha(path)
    ))
    prepare.sync_additive_sources(
        backend,resources,{source:source},{source:[previous_sha]},
    )
    assert target.read_bytes()==b"reviewed current"
    assert target.with_name(source+".kol-backup."+previous_sha).read_bytes()==b"known previous"


def test_unknown_additive_source_drift_is_rejected_before_write(tmp_path):
    backend=tmp_path/"backend";resources=tmp_path/"resources"
    target=backend/"replay_cache.go";desired=resources/"replay_cache.go"
    target.parent.mkdir(parents=True);desired.parent.mkdir(parents=True)
    target.write_bytes(b"unknown edit");desired.write_bytes(b"reviewed current")
    with pytest.raises(RuntimeError,match="additive backend source drift"):
        prepare.sync_additive_sources(
            backend,resources,{"replay_cache.go":"replay_cache.go"},
            {"replay_cache.go":[]},
        )
    assert target.read_bytes()==b"unknown edit"

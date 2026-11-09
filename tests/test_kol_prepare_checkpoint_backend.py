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
REQUIRED_INTERMEDIATE_HASHES = {
    "replay_cache.go": {
        "792324eff3fc222b6c1ba5d59615e1cad5d11c308af8b57fee2cb08004ac2abe",
        "73588c2be306c5a427312198f489adcabd3035afe386d023f73b255ef0725157",
    },
    "replay_cache_test.go": {
        "d928b749e0e4c4e3d4a30329c8b02fa38e883c43a66cc1f4a1e9640b5a93de10",
        "ba8c77fe0e05d89a02c07d44d81386f9d33b199e69bde94ce08d3b8bedd96dad",
    },
}


@pytest.mark.parametrize(
    ("source", "previous_sha"),
    [
        (source, value)
        for source, values in REQUIRED_INTERMEDIATE_HASHES.items()
        for value in sorted(values)
    ],
)
def test_known_maintained_additive_source_upgrades_with_backup(
    tmp_path, monkeypatch, source, previous_sha,
):
    assert REQUIRED_INTERMEDIATE_HASHES[source].issubset(PREVIOUS[source])
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

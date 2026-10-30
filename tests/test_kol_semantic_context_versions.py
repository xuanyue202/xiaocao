"""Instruction revisions retain old immutable delegation and bind new readings."""
import json
from pathlib import Path

import pytest

from xiaocao.kol import semantic_delegation as delegation
from tests.test_kol_semantic_delegation import inputs, _prepare


def test_new_reading_contract_is_bound_and_change_invalidates_existing_packet(inputs, tmp_path, monkeypatch):
    references = tmp_path / "references"
    references.mkdir()
    for name in ("full-contract.md", "durable-knowledge.md", "semantic-analysis.md", "semantic-model-routing.md"):
        (references / name).write_bytes((delegation.REFERENCES / name).read_bytes())
    monkeypatch.setattr(delegation, "REFERENCES", references)
    prepared = _prepare(inputs)
    packet = json.loads(Path(prepared["packet_path"]).read_text())
    assert packet["schema_version"] == 3
    assert packet["contracts"]["analyst_reading"]["path"] == str(references / "semantic-analysis.md")
    assert delegation._load_packet(inputs["request"], prepared["packet_path"]) == packet
    (references / "semantic-analysis.md").write_text("changed reading scope")
    with pytest.raises(delegation.DelegationError):
        delegation._load_packet(inputs["request"], prepared["packet_path"])
    revised = _prepare(inputs)
    assert revised["packet_path"] != prepared["packet_path"]
    assert delegation._load_packet(inputs["request"], revised["packet_path"])["schema_version"] == 3


def test_existing_profile_packet_keeps_exact_v2_prompt_and_idempotent_prepare(inputs):
    directory = inputs["request"].parent / ".semantic_delegation" / delegation._file(inputs["request"])["sha256"]
    directory.mkdir(parents=True)
    path = directory / "context_packet.json"
    profile = delegation.load_analyst_profile()
    packet = delegation._packet(inputs["request"], path, inputs["market"], inputs["household"],
                                profile, schema_version=2)
    prompt = delegation._prompt(packet)
    spawn = {**packet["dispatch_parameters"], "message": prompt}
    for name, raw in (("context_packet.json", delegation._bytes(packet)),
                      ("analyst_prompt.txt", prompt.encode()),
                      ("spawn_arguments.json", delegation._bytes(spawn))):
        (directory / name).write_bytes(raw)
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    assert delegation._load_packet(inputs["request"], path) == packet
    repeated = _prepare(inputs)
    assert repeated["packet_path"] == str(path)
    assert repeated["spawn_arguments"] == spawn
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_unknown_reading_schema_is_not_treated_as_current(inputs):
    prepared = _prepare(inputs)
    path = Path(prepared["packet_path"])
    packet = json.loads(path.read_text())
    packet["schema_version"] = 99
    path.write_bytes(delegation._bytes(packet))
    with pytest.raises(delegation.DelegationError):
        delegation._load_packet(inputs["request"], path)


def test_legacy_packet_can_be_read_but_cannot_be_prepared_under_current_profile(inputs):
    directory = inputs["request"].parent / ".semantic_delegation" / delegation._file(inputs["request"])["sha256"]
    directory.mkdir(parents=True)
    packet_path = directory / "context_packet.json"
    packet = delegation._legacy_packet(inputs["request"], packet_path, inputs["market"], inputs["household"])
    prompt = delegation._legacy_prompt(packet)
    for name, raw in (("context_packet.json", delegation._bytes(packet)),
                      ("analyst_prompt.txt", prompt.encode()),
                      ("spawn_arguments.json", delegation._bytes({**packet["dispatch_parameters"], "message": prompt}))):
        (directory / name).write_bytes(raw)
    before = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    assert delegation._load_packet(inputs["request"], packet_path) == packet
    with pytest.raises(delegation.DelegationError, match="read-only"):
        _prepare(inputs)
    assert {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()} == before

from __future__ import annotations

from pathlib import Path

from xiaocao.kol.runtime_paths import infer_repo_root, resolve_repo_owned_path


def test_resolves_migrated_repo_owned_paths_without_rewriting_receipt(tmp_path):
    repo = tmp_path / "new-checkout"
    anchor = repo / "output" / "live" / "kol_subscription_videos"
    transcript = (
        anchor
        / "enrichment"
        / "version"
        / "artifacts"
        / "job"
        / "transcript.txt"
    )
    transcript.parent.mkdir(parents=True)
    transcript.write_text("immutable evidence\n", encoding="utf-8")
    historical = Path(
        "/Users/old/repo/output/live/kol_subscription_videos/"
        "enrichment/version/artifacts/job/transcript.txt"
    )

    assert infer_repo_root(anchor) == repo
    assert resolve_repo_owned_path(historical, anchor=anchor) == transcript


def test_does_not_remap_paths_outside_the_kol_repo_trees(tmp_path):
    anchor = tmp_path / "repo" / "output" / "live" / "kol"
    external = Path("/Users/old/private/secret.txt")

    assert resolve_repo_owned_path(external, anchor=anchor) == external


def test_existing_historical_path_wins(tmp_path):
    anchor = tmp_path / "new" / "output" / "live" / "kol"
    historical = tmp_path / "old" / "output" / "live" / "receipt.json"
    historical.parent.mkdir(parents=True)
    historical.write_text("{}\n", encoding="utf-8")

    assert resolve_repo_owned_path(historical, anchor=anchor) == historical

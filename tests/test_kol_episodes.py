from __future__ import annotations

from xiaocao.kol.episodes import assemble_video_units


def _video(
    path: str,
    identity: str,
    *,
    version: str | None = None,
    episode_id: str | None = None,
    episode_title: str | None = None,
    part_index: int | None = None,
    part_count: int | None = None,
) -> dict:
    row = {
        "identity": identity,
        "version_key": version or f"version-{identity}",
        "provider_identity_sha256": (identity * 64)[:64],
        "source": "baidu_private_folder",
        "author": "路西法",
        "path": path,
        "name": path.rsplit("/", 1)[-1],
        "media_type": "video",
        "size": 100,
        "modified_at": 1_784_456_551,
        "version_first_seen_at": "2026-07-25T16:00:00+08:00",
        "present": True,
    }
    if episode_id is not None:
        row["episode_id"] = episode_id
    if episode_title is not None:
        row["episode_title"] = episode_title
    if part_index is not None:
        row["part_index"] = part_index
    if part_count is not None:
        row["part_count"] = part_count
    return row


def test_auto_groups_arbitrary_numeric_part_count_and_mixed_common_markers():
    rows = [
        _video("/课程/主题/发布会 Part 1.mp4", "a"),
        _video("/课程/主题/发布会（2）.mp4", "b"),
        _video("/课程/主题/发布会_03.mp4", "c"),
        _video("/课程/主题/发布会 第4段.mkv", "d"),
    ]

    assembled = assemble_video_units(rows)

    assert assembled["ambiguities"] == []
    assert len(assembled["units"]) == 1
    episode = assembled["units"][0]
    assert episode["is_episode"] is True
    assert episode["name"] == "发布会.episode"
    assert episode["completion_contract"] == "quiescent_filename_group"
    assert episode["settle_seconds"] == 300
    assert [part["part_index"] for part in episode["parts"]] == [1, 2, 3, 4]
    assert [part["name"] for part in episode["parts"]] == [
        "发布会 Part 1.mp4",
        "发布会（2）.mp4",
        "发布会_03.mp4",
        "发布会 第4段.mkv",
    ]


def test_auto_groups_chinese_or_semantic_labels_without_assuming_three_parts():
    two_part = assemble_video_units(
        [
            _video("/课程/主题/复盘（上）.mp4", "a"),
            _video("/课程/主题/复盘（下）.mp4", "b"),
        ]
    )
    four_part = assemble_video_units(
        [
            _video("/课程/主题/周报（一）.mp4", "c"),
            _video("/课程/主题/周报（二）.mp4", "d"),
            _video("/课程/主题/周报（三）.mp4", "e"),
            _video("/课程/主题/周报（四）.mp4", "f"),
        ]
    )

    assert [
        part["part_index"] for part in two_part["units"][0]["parts"]
    ] == [1, 2]
    assert [
        part["part_index"] for part in four_part["units"][0]["parts"]
    ] == [1, 2, 3, 4]


def test_explicit_episode_metadata_supports_arbitrary_filenames_and_order():
    rows = [
        _video(
            "/课程/主题/上午场-final.mp4",
            "a",
            episode_id="launch-day",
            episode_title="新品发布日",
            part_index=2,
            part_count=3,
        ),
        _video(
            "/课程/主题/keynote.mp4",
            "b",
            episode_id="launch-day",
            episode_title="新品发布日",
            part_index=1,
            part_count=3,
        ),
        _video(
            "/课程/主题/Q&A.mp4",
            "c",
            episode_id="launch-day",
            episode_title="新品发布日",
            part_index=3,
            part_count=3,
        ),
    ]

    assembled = assemble_video_units(rows)

    assert assembled["ambiguities"] == []
    episode = assembled["units"][0]
    assert episode["name"] == "新品发布日.episode"
    assert episode["completion_contract"] == "declared_part_count"
    assert episode["settle_seconds"] == 0
    assert [part["name"] for part in episode["parts"]] == [
        "keynote.mp4",
        "上午场-final.mp4",
        "Q&A.mp4",
    ]


def test_incomplete_or_duplicate_part_order_pauses_instead_of_guessing():
    incomplete = assemble_video_units(
        [
            _video("/课程/主题/复盘 Part 1.mp4", "a"),
            _video("/课程/主题/复盘 Part 3.mp4", "b"),
        ]
    )
    duplicate = assemble_video_units(
        [
            _video("/课程/主题/复盘 Part 1.mp4", "c"),
            _video("/课程/主题/复盘（1）.mp4", "d"),
        ]
    )

    assert incomplete["units"] == []
    assert incomplete["ambiguities"][0]["reason"] == "incomplete_episode"
    assert duplicate["units"] == []
    assert duplicate["ambiguities"][0]["reason"] == "ambiguous_episode_order"


def test_single_part_marker_waits_for_companions_but_plain_video_is_standalone():
    assembled = assemble_video_units(
        [
            _video("/课程/主题/复盘 Part 1.mp4", "a"),
            _video("/课程/主题/7月20日.mp4", "b"),
        ]
    )

    assert [unit["name"] for unit in assembled["units"]] == ["7月20日.mp4"]
    assert assembled["ambiguities"][0]["reason"] == (
        "episode_waiting_for_companions"
    )


def test_single_weak_suffix_is_standalone_instead_of_manifest_pause_noise():
    assembled = assemble_video_units(
        [
            _video("/课程/主题/SVID_20241023_210947_1.mp4", "a"),
            _video("/课程/主题/课程名称 (1).mp4", "b"),
        ]
    )

    assert assembled["ambiguities"] == []
    assert [unit["name"] for unit in assembled["units"]] == [
        "SVID_20241023_210947_1.mp4",
        "课程名称 (1).mp4",
    ]

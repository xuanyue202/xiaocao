"""Guard the native cancel capability probe against visible order mutations."""

from pathlib import Path


def test_cancel_capability_probe_returns_before_any_selection_click() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift"
    ).read_text(encoding="utf-8")
    routine = source[
        source.index("private func performCancel(") : source.index(
            "private func readQuery("
        )
    ]

    probe_return = routine.index("if selectionProbeOnly")
    first_selection_click = routine.index("postSingleLeftClick")

    assert probe_return < first_selection_click

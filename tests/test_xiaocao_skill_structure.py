from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".codex" / "skills" / "xiaocao-trading"
SKILL_MD = SKILL_DIR / "SKILL.md"

EXPECTED_BRANCHES = {
    "automation-morning.md",
    "automation-intraday.md",
    "automation-eod.md",
    "automation-weekly.md",
    "scheduling.md",
    "market-data.md",
    "strategy-and-backtests.md",
    "research-flywheels.md",
}


def test_xiaocao_skill_routes_to_existing_branch_files() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")

    for name in EXPECTED_BRANCHES:
        assert f"(references/{name})" in text
        assert (SKILL_DIR / "references" / name).is_file()


def test_xiaocao_skill_local_markdown_links_resolve() -> None:
    markdown_files = [SKILL_MD, *(SKILL_DIR / "references").glob("*.md")]

    for source in markdown_files:
        text = source.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+\.md)\)", text):
            assert (source.parent / target).resolve().is_file(), (
                f"broken Markdown link in {source}: {target}"
            )

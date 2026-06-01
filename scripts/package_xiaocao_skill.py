"""Package the distributable xiaocao-trading Codex skill.

The skill is self-contained: it bundles a minimal xiaocao runtime under
`assets/xiaocao-runtime` so recipients do not need this repository checked out.

Output:
    output/xiaocao-trading-skill.zip
    output/xiaocao-trading-skill.sha256
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILL_DIR = Path.home() / ".codex" / "skills" / "xiaocao-trading"
DEFAULT_OUTPUT_DIR = ROOT / "output"

RUNTIME_ITEMS = [
    "src",
    "scripts",
    "tests",
    "docs",
    "pyproject.toml",
    "README.md",
    "xiaocao.yaml.example",
    "stocks.json",
]


def _ignore_runtime_noise(_: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if (
            name == "__pycache__"
            or name == ".DS_Store"
            or name.endswith(".pyc")
            or name.endswith(".pyo")
            or name.endswith(".egg-info")
        ):
            ignored.add(name)
    return ignored


def _copy_item(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Required runtime item is missing: {src}")
    if src.is_dir():
        shutil.copytree(src, dst, ignore=_ignore_runtime_noise)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def refresh_runtime(skill_dir: Path) -> Path:
    runtime_dir = skill_dir / "assets" / "xiaocao-runtime"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True)

    for item in RUNTIME_ITEMS:
        _copy_item(ROOT / item, runtime_dir / item)

    for rel in ("output/live", "reports/premarket", "reports/afterclose"):
        (runtime_dir / rel).mkdir(parents=True, exist_ok=True)

    return runtime_dir


def validate_skill(skill_dir: Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    runtime = skill_dir / "assets" / "xiaocao-runtime"
    required = [
        skill_md,
        openai_yaml,
        runtime / "src" / "xiaocao" / "cli.py",
        runtime / "scripts" / "live_recommend.py",
        runtime / "scripts" / "live_monitor.py",
        runtime / "pyproject.toml",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required package files:\n" + "\n".join(missing))

    text = skill_md.read_text(encoding="utf-8")
    if "name: xiaocao-trading" not in text or "description:" not in text:
        raise ValueError("SKILL.md frontmatter must include name and description")


def smoke_test(runtime_dir: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    subprocess.run(
        [sys.executable, "-m", "xiaocao", "--help"],
        cwd=runtime_dir,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def zip_skill(skill_dir: Path, output_dir: Path) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / "xiaocao-trading-skill.zip"
    sha_path = output_dir / "xiaocao-trading-skill.sha256"
    if zip_path.exists():
        zip_path.unlink()
    if sha_path.exists():
        sha_path.unlink()

    base = skill_dir.parent
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(base))

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return zip_path, digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-dir", type=Path, default=DEFAULT_SKILL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-smoke-test", action="store_true")
    args = parser.parse_args()

    skill_dir = args.skill_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not skill_dir.exists():
        raise SystemExit(f"ERROR: skill directory not found: {skill_dir}")

    runtime_dir = refresh_runtime(skill_dir)
    validate_skill(skill_dir)
    if not args.no_smoke_test:
        smoke_test(runtime_dir)

    zip_path, digest = zip_skill(skill_dir, output_dir)
    print(f"skill_dir: {skill_dir}")
    print(f"runtime:   {runtime_dir}")
    print(f"zip:       {zip_path}")
    print(f"sha256:    {digest}")
    print(f"sha_file:  {output_dir / 'xiaocao-trading-skill.sha256'}")


if __name__ == "__main__":
    main()

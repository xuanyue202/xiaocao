"""Package and install the repo-maintained xiaocao-trading Codex skill.

The repo copy under `.codex/skills/xiaocao-trading/` is the source of truth.
This script refreshes its generated runtime bundle from the current checkout,
optionally links or copies that skill to the local Codex install directory, then
creates a distributable zip.

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
DEFAULT_SKILL_DIR = ROOT / ".codex" / "skills" / "xiaocao-trading"
DEFAULT_INSTALL_DIR = Path.home() / ".codex" / "skills" / "xiaocao-trading"
DEFAULT_OUTPUT_DIR = ROOT / "output"
PACKAGE_DIR_NAME = "xiaocao-trading"

SKILL_REFERENCE_FILES = [
    "automation-morning.md",
    "automation-intraday.md",
    "automation-eod.md",
    "automation-weekly.md",
    "scheduling.md",
    "market-data.md",
    "strategy-and-backtests.md",
    "research-flywheels.md",
]

RUNTIME_ITEMS = [
    "src",
    "scripts",
    "tests",
    "docs",
    "kronos_screen/STATE.md",
    "kronos_screen/model/spec.json",
    "kronos_screen/scripts",
    "reference/experience",
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
        *(skill_dir / "references" / name for name in SKILL_REFERENCE_FILES),
        runtime / "src" / "xiaocao" / "cli.py",
        runtime / "src" / "xiaocao" / "live" / "safety.py",
        runtime / "scripts" / "auto_daily.sh",
        runtime / "scripts" / "authorize_live.py",
        runtime / "scripts" / "live_recommend.py",
        runtime / "scripts" / "live_monitor.py",
        runtime / "kronos_screen" / "scripts" / "paper_record.py",
        runtime / "kronos_screen" / "scripts" / "eod_capture.py",
        runtime / "kronos_screen" / "scripts" / "forward_eval.py",
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
    subprocess.run(["bash", "-n", "scripts/auto_daily.sh"], cwd=runtime_dir, check=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "scripts/authorize_live.py",
            "scripts/live_recommend.py",
            "scripts/live_monitor.py",
            "kronos_screen/scripts/paper_record.py",
            "src/xiaocao/live/safety.py",
        ],
        cwd=runtime_dir,
        env=env,
        check=True,
    )


def _remove_path(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def install_skill(skill_dir: Path, install_dir: Path, mode: str) -> None:
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    if mode == "symlink":
        if install_dir.is_symlink() and install_dir.resolve() == skill_dir:
            return
        if install_dir.exists() and install_dir.resolve() == skill_dir:
            return
        _remove_path(install_dir)
        install_dir.symlink_to(skill_dir, target_is_directory=True)
        return

    if mode != "copy":
        raise ValueError(f"unknown install mode: {mode}")

    tmp_dir = install_dir.parent / f".{install_dir.name}.tmp"
    _remove_path(tmp_dir)
    shutil.copytree(skill_dir, tmp_dir, ignore=_ignore_runtime_noise)
    _remove_path(install_dir)
    tmp_dir.rename(install_dir)


def zip_skill(skill_dir: Path, output_dir: Path) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / "xiaocao-trading-skill.zip"
    sha_path = output_dir / "xiaocao-trading-skill.sha256"
    if zip_path.exists():
        zip_path.unlink()
    if sha_path.exists():
        sha_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file():
                arcname = Path(PACKAGE_DIR_NAME) / path.relative_to(skill_dir)
                zf.write(path, arcname)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return zip_path, digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=DEFAULT_SKILL_DIR,
        help="repo-maintained skill directory; default: ./.codex/skills/xiaocao-trading",
    )
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=DEFAULT_INSTALL_DIR,
        help="local Codex install destination; default: ~/.codex/skills/xiaocao-trading",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-install", action="store_true", help="refresh/package only; do not touch ~/.codex")
    parser.add_argument(
        "--install-mode",
        choices=("symlink", "copy"),
        default="symlink",
        help="how to expose the repo skill to Codex; default: symlink",
    )
    parser.add_argument("--no-smoke-test", action="store_true")
    args = parser.parse_args()

    skill_dir = args.skill_dir.expanduser().resolve()
    install_dir = args.install_dir.expanduser()
    if not install_dir.is_absolute():
        install_dir = Path.cwd() / install_dir
    install_dir = install_dir.absolute()
    output_dir = args.output_dir.expanduser().resolve()
    if not skill_dir.exists():
        raise SystemExit(f"ERROR: skill directory not found: {skill_dir}")

    runtime_dir = refresh_runtime(skill_dir)
    validate_skill(skill_dir)
    if not args.no_smoke_test:
        smoke_test(runtime_dir)
    if not args.no_install:
        install_skill(skill_dir, install_dir, args.install_mode)

    zip_path, digest = zip_skill(skill_dir, output_dir)
    print(f"skill_dir: {skill_dir}")
    print(f"runtime:   {runtime_dir}")
    if not args.no_install:
        print(f"installed: {install_dir} ({args.install_mode})")
    print(f"zip:       {zip_path}")
    print(f"sha256:    {digest}")
    print(f"sha_file:  {output_dir / 'xiaocao-trading-skill.sha256'}")


if __name__ == "__main__":
    main()

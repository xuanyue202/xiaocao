from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Settings:
    base_url: str = "https://p-xcapi.kjap1.cn"
    timeout: float = 10
    retries: int = 3
    exchange: str = "SSE"
    output_format: str = "table"
    data_dir: str = "results"
    output_dir: str = "output"
    log_level: str = "info"
    hpqb_state: int = 0
    lpdx_state: int = 0
    block_model: int = 1
    category_model: int = 0


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(config_path: str | None = None) -> Settings:
    candidates = []
    if config_path:
        candidates.append(Path(config_path))
    elif os.environ.get("XIAOCAO_CONFIG"):
        candidates.append(Path(os.environ["XIAOCAO_CONFIG"]))
    else:
        candidates.extend([Path.cwd() / "xiaocao.yaml", Path.home() / ".xiaocao" / "config.yaml"])

    data: dict[str, Any] = {}
    for candidate in candidates:
        data = _read_yaml(candidate)
        if data:
            break

    settings = Settings(
        base_url=data.get("api", {}).get("base_url", Settings.base_url),
        timeout=data.get("api", {}).get("timeout", Settings.timeout),
        retries=data.get("api", {}).get("retries", Settings.retries),
        exchange=data.get("defaults", {}).get("exchange", Settings.exchange),
        output_format=data.get("defaults", {}).get("output_format", Settings.output_format),
        data_dir=data.get("defaults", {}).get("data_dir", Settings.data_dir),
        output_dir=data.get("defaults", {}).get("output_dir", Settings.output_dir),
        log_level=data.get("logging", {}).get("level", Settings.log_level),
        hpqb_state=data.get("strategy", {}).get("hpqb_state", Settings.hpqb_state),
        lpdx_state=data.get("strategy", {}).get("lpdx_state", Settings.lpdx_state),
        block_model=data.get("strategy", {}).get("block_model", Settings.block_model),
        category_model=data.get("strategy", {}).get("category_model", Settings.category_model),
    )

    settings.base_url = os.environ.get("XIAOCAO_BASE_URL", settings.base_url)
    settings.timeout = float(os.environ.get("XIAOCAO_TIMEOUT", settings.timeout))
    settings.retries = int(os.environ.get("XIAOCAO_RETRIES", settings.retries))
    settings.log_level = os.environ.get("XIAOCAO_LOG_LEVEL", settings.log_level)
    return settings

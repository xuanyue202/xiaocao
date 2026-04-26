from __future__ import annotations

import ast
import csv
import json
from pathlib import Path
from typing import Any

from xiaocao.api.catalog import SORT_V2_ALIASES, SORT_V2_FIELDS
from xiaocao.api.errors import NoDataError, XiaocaoError


GROUP_FIELDS = {
    "0": "jsjl",
    "1": "xcjw",
    "2": "jssb",
    "3": "cjs",
    "jieli": "jsjl",
    "jingwang": "xcjw",
    "hpqb": "jssb",
    "qibao": "jssb",
    "dixi": "cjs",
}

SORT_ID_FIELDS = {
    37: "jsjl",
    38: "xcjw",
    39: "jssb",
    40: "cjs",
    41: "dwcjs",
    44: "jsjlTest",
    45: "jssbTest",
    46: "cjsTest",
    47: "directionCjs",
    48: "xcjwV2",
    49: "jssbV2",
    50: "cjsV2",
    51: "jsjlBlock",
    52: "jssbBlock",
    53: "cjsBlock",
    54: "directionCjsV2",
    55: "cgykValue",
    56: "htykValue",
    57: "minuteCgykValue",
    58: "minuteHtykValue",
    59: "atraderate30d",
    60: "atraderate10d",
    "cjs": "cjs",
    "dixi": "cjs",
    "xcjw": "xcjw",
    "jingwang": "xcjw",
    "jsjl": "jsjl",
    "jieli": "jsjl",
    "jssb": "jssb",
    "hpqb": "jssb",
    "xiaocaoJSJL": "jsjl",
    "xiaocaoXCJW": "xcjw",
    "xiaocaoJSSB": "jssb",
    "xiaocaoCJS": "cjs",
    "xiaocaoDWCJS": "dwcjs",
}
for key, item in SORT_V2_FIELDS.items():
    SORT_ID_FIELDS.setdefault(item.value, key)
    SORT_ID_FIELDS.setdefault(key, key)
for alias, target in SORT_V2_ALIASES.items():
    SORT_ID_FIELDS.setdefault(alias, SORT_ID_FIELDS.get(target, target))


class LocalDataSource:
    def __init__(self, data_dir: str = "results") -> None:
        self.data_dir = Path(data_dir)

    def latest_date(self, max_date: str | None = None) -> str:
        dates = sorted(path.name[:10] for path in self.data_dir.glob("*_detail.csv"))
        if max_date:
            dates = [item for item in dates if item <= max_date]
        if not dates:
            raise NoDataError(f"No local detail CSV files found in {self.data_dir}")
        return dates[-1]

    def get_pool(self, date: str, group: str | int) -> list[str]:
        field = GROUP_FIELDS.get(str(group), str(group))
        rows = self.get_stock_index(date)
        filtered = [row for row in rows if _to_float(row.get(field)) != 0]
        filtered.sort(key=lambda row: _to_float(row.get(field)), reverse=True)
        return [row["code"] for row in filtered if row.get("code")]

    def get_stock_index(self, date: str, codes: list[str] | None = None) -> list[dict[str, Any]]:
        path = self.data_dir / f"{date}_detail.csv"
        if not path.exists():
            raise NoDataError(f"Missing local detail file: {path}")
        rows = _read_csv(path)
        if codes is None:
            return rows
        lookup = {row.get("code"): row for row in rows}
        return [lookup[code] for code in codes if code in lookup]

    def sort_codes(
        self,
        date: str,
        codes: list[str] | None = None,
        sort_id: int | str = "xcjw",
        descending: bool = True,
        target_type: int | str = "stock",
    ) -> list[str]:
        sort_field = SORT_ID_FIELDS.get(sort_id)
        if sort_field is None:
            raise XiaocaoError(
                f"Local source does not know sort-id {sort_id}. "
                f"Known local mappings: {', '.join(str(key) for key in SORT_ID_FIELDS)}"
            )
        rows = self.get_stock_index(date, codes)
        rows.sort(key=lambda row: _to_float(row.get(sort_field)), reverse=descending)
        return [row["code"] for row in rows if row.get("code")]

    def get_industry_block_rank(self, date: str, model: int = 1) -> list[dict[str, Any]]:
        path = self.data_dir / "archive" / "xiaocao_industry_block_all_0.csv"
        rows = _read_csv(path)
        return [row for row in rows if row.get("date") == date or row.get("tradeDate") == date]

    def get_block_category_rank(self, date: str, model: int = 0) -> list[dict[str, Any]]:
        json_path = self.data_dir / "archive" / "xiaocao_industry_block_category_rank_all_local_0.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return [_coerce_row(row) for row in data if row.get("tradeDate") == date]
        path = self.data_dir / "archive" / "xiaocao_industry_block_category_rank_local_0.csv"
        rows = _read_csv(path)
        return [row for row in rows if row.get("tradeDate") == date]

    def get_direction_codes(
        self,
        date: str,
        block_code: str | None = None,
        category_code: str | None = None,
    ) -> list[str]:
        rows = self.get_stock_index(date)
        output = []
        for row in rows:
            block_codes = set(row.get("blockCodeList") or []) | set(row.get("industryBlockCodeList") or [])
            category_codes = set(row.get("blockCategoryCodeList") or [])
            if block_code and block_code in block_codes:
                output.append(row["code"])
            elif category_code and category_code in category_codes:
                output.append(row["code"])
        return output


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise NoDataError(f"Missing local data file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [_coerce_row(row) for row in csv.DictReader(handle)]


def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in row.items():
        if value == "":
            result[key] = None
        elif key.endswith("List") and isinstance(value, str):
            try:
                parsed = ast.literal_eval(value)
                result[key] = parsed if isinstance(parsed, list) else value
            except (SyntaxError, ValueError):
                result[key] = value
        else:
            result[key] = _coerce_scalar(value)
    return result


def _coerce_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0

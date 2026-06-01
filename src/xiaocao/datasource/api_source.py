from __future__ import annotations

from typing import Any

from xiaocao.api.catalog import STOCK_GROUPS, resolve_group
from xiaocao.api.client import XiaocaoClient


GROUPS = {key: item.value for key, item in STOCK_GROUPS.items()}


class ApiDataSource:
    def __init__(self, client: XiaocaoClient, hpqb_state: int = 0, lpdx_state: int = 0) -> None:
        self.client = client
        self.hpqb_state = hpqb_state
        self.lpdx_state = lpdx_state

    def get_pool(self, date: str, group: str | int) -> list[str]:
        group_id = resolve_group(group)
        return self.client.get_code_list_v2(date, group_id, self.hpqb_state, self.lpdx_state)

    def get_stock_index(self, date: str, codes: list[str]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for i in range(0, len(codes), 80):
            output.extend(
                self.client.get_xiao_cao_index_v2(
                    date,
                    codes[i : i + 80],
                    self.hpqb_state,
                    self.lpdx_state,
                )
            )
        # The backend may return a mapping or a list whose order is not the
        # requested order. Strategy rules scan sorted pools with early-stop
        # score floors, so preserving the caller's sorted `codes` order is
        # part of the datasource contract.
        by_code: dict[str, dict[str, Any]] = {}
        for row in output:
            if not isinstance(row, dict):
                continue
            code = row.get("code") or row.get("stockCode") or row.get("stockId")
            if code:
                by_code[str(code)] = row
        if not by_code:
            return output
        requested_codes = set(codes)
        ordered = [by_code[code] for code in codes if code in by_code]
        extras = [
            row for row in output
            if isinstance(row, dict)
            and str(row.get("code") or row.get("stockCode") or row.get("stockId") or "") not in requested_codes
        ]
        return ordered + extras

    def sort_codes(
        self,
        date: str,
        codes: list[str],
        sort_id: int | str = 40,
        descending: bool = True,
        target_type: int | str = "stock",
    ) -> list[str]:
        rows = self.client.sort_v2(
            codes,
            sort_id=sort_id,
            sort_type=descending,
            type_=target_type,
            date=date,
            hpqb_state=self.hpqb_state,
            lpdx_state=self.lpdx_state,
        )
        result = []
        for row in rows:
            if isinstance(row, str):
                result.append(row)
            elif isinstance(row, dict):
                code = row.get("code") or row.get("stockCode") or row.get("stockId")
                if code:
                    result.append(code)
        requested = set(codes)
        filtered = [code for code in result if code in requested]
        return filtered or list(codes)

    def get_industry_block_rank(self, date: str, model: int = 1) -> list[dict[str, Any]]:
        return self.client.get_industry_block_rank(date, model)

    def get_block_category_rank(self, date: str, model: int = 0) -> list[dict[str, Any]]:
        return self.client.get_block_category_rank_v3(date, model)

    def get_direction_codes(
        self,
        date: str,
        block_code: str | None = None,
        category_code: str | None = None,
    ) -> list[str]:
        result = self.client.get_code_by_xiao_cao_block(
            date,
            blockCodeList=block_code or "",
            industryBlockCodeList=block_code or "",
            categoryCodeList=category_code or "",
        )
        return _extract_codes(result)


def _extract_codes(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        codes: list[str] = []
        for item in value:
            codes.extend(_extract_codes(item))
        return _dedupe(codes)
    if isinstance(value, dict):
        for key in ("data", "codes", "stockCodes", "stockIds", "codeList", "list"):
            if key in value:
                return _extract_codes(value[key])
        code = value.get("code") or value.get("stockCode") or value.get("stockId")
        return [code] if code else []
    return []


def _dedupe(codes: list[str]) -> list[str]:
    seen = set()
    output = []
    for code in codes:
        if code and code not in seen:
            seen.add(code)
            output.append(code)
    return output

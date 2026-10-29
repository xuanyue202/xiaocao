from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
import hashlib
import json
import copy
import time
from pathlib import Path
from xiaocao.utils.atomic_files import atomic_write

from xiaocao.live.source_observation import observation_current

from xiaocao.api.catalog import STOCK_GROUPS, resolve_group
from xiaocao.api.client import XiaocaoClient
from xiaocao.api.errors import ApiSchemaError, ApiSourceNotReadyError


GROUPS = {key: item.value for key, item in STOCK_GROUPS.items()}


class ApiDataSource:
    def __init__(self, client: XiaocaoClient, hpqb_state: int = 0, lpdx_state: int = 0,
                 *, resolve_security_universe: bool = False) -> None:
        self.client = client
        self.hpqb_state = hpqb_state
        self.lpdx_state = lpdx_state
        self.observations: list[dict[str, Any]] = []
        self.readiness: dict[str, Any] = {}
        self._observe_enabled = False
        self._requests = {}
        self._validated = {}
        self._fresh_keys = set()
        self._failed_keys = set()
        # Enable only for current capture: today's directory cannot filter history.
        self.resolve_security_universe = resolve_security_universe
        self._security_codes: set[str] | None = None
        self._security_directory_sha256: str | None = None

    def begin_observation(self, attempt: int, *, retry_missing: bool = False) -> None:
        retained = {k:v for k,v in self._validated.items()
                    if v[1].get("status") in {"populated", "empty_confirmed"}
                    and observation_current(v[1], now=datetime.now(timezone.utc))} if retry_missing else {}
        self._fresh_keys = self._failed_keys | {k for k, v in self._validated.items()
                            if v[1].get("status") not in {"populated", "empty_confirmed"}}
        self._failed_keys = set()
        self._observe_enabled = True
        self.observations = []
        self.readiness = {"attempt": attempt, "sources": self.observations}
        self._requests = {}
        self._validated = retained
        self._security_codes = None
        self._security_directory_sha256 = None

    def reuse_ready_observation(self, attempt: int) -> bool:
        """Keep one complete, still-current source version instead of chasing ticks."""
        reusable = bool(self._requests) and self.observation_is_current()
        if reusable:
            self.readiness["attempt"] = attempt
            self.readiness["confirmation"] = {"unchanged": True, "reused": True,
                "request_count": len(self._requests)}
        return reusable

    def observation_is_current(self) -> bool:
        if not self.observations:
            return False
        return all(r.get("status") in {"populated", "empty_confirmed"}
                   and observation_current(r, now=datetime.now(timezone.utc)) for r in self.observations)

    def revalidate_observation(self, attempt: int) -> bool:
        previous = dict(self._requests)
        previous_records = dict(self._validated)
        self.begin_observation(attempt)
        unchanged = True
        for key, (kind, day, fetch, codes, cache_key, expected) in previous.items():
            self._observe(kind, day, fetch, requested_codes=codes, cache_key=cache_key)
            record = self.observations[-1]
            if record.get("response_sha256") == expected:
                record.update({k:v for k,v in previous_records[key][1].items()
                               if k in {"ranked_requested_count", "unranked_codes", "status",
                                        "raw_code_count", "admitted_code_count", "excluded_codes",
                                        "exclusion_reason", "security_directory_sha256"}})
            unchanged = unchanged and record.get("response_sha256") == expected
        self.readiness["confirmation"] = {"unchanged": unchanged, "request_count": len(previous)}
        return bool(previous) and unchanged

    def reuse_validated_observation(self):
        # A changed universe can reuse just-confirmed input responses by exact
        # query key while exposing only the inputs actually used by the rerun.
        self.observations.clear()
        self._requests.clear()
        self._security_codes = None
        self._security_directory_sha256 = None

    def _observe(self, kind: str, date: str, fetch, *, requested_codes=None, cache_key=()):
        if not self._observe_enabled:
            return fetch()
        stamp = datetime.now(timezone.utc).isoformat()
        key = (kind, date, tuple(requested_codes or ()), tuple(cache_key))
        if key in self._validated:
            rows, record, request = self._validated[key]
            record = copy.deepcopy(record)
            self.observations.append(record)
            self._validated[key] = (rows, record, request)
            self._requests[key] = request
            return copy.deepcopy(rows)
        started = time.monotonic()
        try:
            # A known empty/partial live observation must not read the same
            # cached failure for ten seconds. Only its exact request bypasses.
            if key in self._fresh_keys and isinstance(self.client, XiaocaoClient):
                with self.client.uncached_reads():
                    rows = fetch()
            else:
                rows = fetch()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                observed_date = row.get("tradeDate") or row.get("trade_date")
                if observed_date and str(observed_date).replace("-", "")[:8] != date.replace("-", "")[:8]:
                    try:
                        observed_day = datetime.strptime(str(observed_date).replace("-", "")[:8], "%Y%m%d").date()
                        requested_day = datetime.strptime(date.replace("-", "")[:8], "%Y%m%d").date()
                    except ValueError as exc:
                        raise ApiSchemaError("MORNING_SOURCE_DATE_INVALID:" + kind) from exc
                    if observed_day < requested_day:
                        raise ApiSourceNotReadyError("MORNING_SOURCE_DATE_MISMATCH:" + kind)
                    raise ApiSchemaError("MORNING_SOURCE_DATE_MISMATCH:" + kind)
        except Exception as exc:
            self._failed_keys.add(key)
            self.observations.append({"source": kind, "requested_date": date,
                                      "observed_at": stamp, "status": "error",
                                      "error_type": type(exc).__name__})
            raise
        missing = []
        if requested_codes:
            found = {str(row) if isinstance(row, str) else
                     str(row.get("code") or row.get("stockCode") or row.get("stockId") or "")
                     for row in rows if isinstance(row, (dict, str))}
            missing = sorted(set(requested_codes) - found)
        response = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str).encode()
        response_hash = hashlib.sha256(response).hexdigest()
        response_path = Path("output/live/morning_sources/normalized") / (response_hash + ".json")
        atomic_write(response_path, response, immutable=True)
        self.observations.append({
            "source": kind, "requested_date": date, "observed_at": stamp,
            "status": "partial" if missing else "populated" if rows else "empty_unconfirmed",
            "row_count": len(rows), "missing_codes": missing,
            "response_sha256": response_hash, "response_path": str(response_path.resolve()),
            "requested_codes": list(requested_codes or []),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 6),
        })
        record = self.observations[-1]
        if kind == "security_directory" and getattr(self.client, "stock_info_evidence", None):
            record["raw_response"] = copy.deepcopy(self.client.stock_info_evidence)
        request = (kind, date, fetch, tuple(requested_codes or ()), tuple(cache_key), record["response_sha256"])
        self._requests[key] = request
        self._validated[key] = (copy.deepcopy(rows), record, request)
        return rows

    def get_pool(self, date: str, group: str | int) -> list[str]:
        group_id = resolve_group(group)
        self._load_security_directory(date)
        codes = self._observe(f"pool:{group}", date, lambda: self.client.get_code_list_v2(
            date, group_id, self.hpqb_state, self.lpdx_state))
        return self._admit_security_codes(codes)

    def _load_security_directory(self, date: str) -> None:
        if not self.resolve_security_universe or self._security_codes is not None:
            return

        def fetch():
            rows = self.client.stock_info(use_cache=False, strict=True)
            if not rows:
                raise ApiSourceNotReadyError("MORNING_SECURITY_DIRECTORY_EMPTY")
            if (not isinstance(rows, list) or any(
                    not isinstance(r, dict) or not isinstance(r.get("stockId"), str)
                    or "." not in r["stockId"] or not r["stockId"].strip() for r in rows)):
                raise ApiSchemaError("MORNING_SECURITY_DIRECTORY_INVALID")
            return rows

        rows = self._observe("security_directory", date, fetch)
        self._security_codes = {r["stockId"] for r in rows}
        if self._observe_enabled:
            record = self.observations[-1]
            self._security_directory_sha256 = record["response_sha256"]

    def _admit_security_codes(self, codes: list[str]) -> list[str]:
        if not self.resolve_security_universe:
            return codes
        admitted = [code for code in codes if code in self._security_codes]
        if self._observe_enabled:
            self.observations[-1].update(
                raw_code_count=len(codes), admitted_code_count=len(admitted),
                excluded_codes=sorted(set(codes) - self._security_codes),
                exclusion_reason="NOT_IN_SECURITY_DIRECTORY",
                security_directory_sha256=self._security_directory_sha256,
            )
        return admitted

    def get_stock_index(self, date: str, codes: list[str]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for i in range(0, len(codes), 80):
            output.extend(
                self._observe("stock_index", date, lambda chunk=tuple(codes[i : i + 80]): self.client.get_xiao_cao_index_v2(
                    date,
                    list(chunk),
                    self.hpqb_state,
                    self.lpdx_state,
                ), requested_codes=codes[i : i + 80])
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
        if not codes:
            return []
        rows = self._observe(f"sort:{sort_id}", date, lambda selected=tuple(codes): self.client.sort_v2(
            list(selected),
            sort_id=sort_id,
            sort_type=descending,
            type_=target_type,
            date=date,
            hpqb_state=self.hpqb_state,
            lpdx_state=self.lpdx_state,
        ), cache_key=(tuple(codes), descending, target_type))
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
        if self._observe_enabled:
            # sort_v2 publishes a ranking, not a permutation: the official
            # frontend intersects it with stockIds and unranked stocks can
            # be absent. Keep that omission visible without requiring every
            # unranked universe member to acquire a score. The subsequent
            # stock_index reads still require each selected code's detail.
            self.observations[-1].update(
                ranked_requested_count=len(set(filtered)),
                unranked_codes=sorted(requested - set(filtered)),
            )
            if codes and not filtered:
                self.observations[-1]["status"] = "partial"
        return filtered or list(codes)

    def get_industry_block_rank(self, date: str, model: int = 1) -> list[dict[str, Any]]:
        return self._observe("industry_rank", date, lambda: self.client.get_industry_block_rank(date, model), cache_key=(model,))

    def get_block_category_rank(self, date: str, model: int = 0) -> list[dict[str, Any]]:
        return self._observe("category_rank", date, lambda: self.client.get_block_category_rank_v3(date, model), cache_key=(model,))

    def get_direction_codes(
        self,
        date: str,
        block_code: str | None = None,
        category_code: str | None = None,
    ) -> list[str]:
        self._load_security_directory(date)
        result = self._observe("direction_codes", date, lambda: self.client.get_code_by_xiao_cao_block(
            date,
            blockCodeList=block_code or "",
            industryBlockCodeList=block_code or "",
            categoryCodeList=category_code or "",
        ), cache_key=(block_code, category_code))
        return self._admit_security_codes(_extract_codes(result))


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

"""Regenerate docs/reference_api_inventory.md from ENDPOINTS in api/catalog.py.

Run from the repo root:

    PYTHONPATH=src python3 scripts/render_inventory.py

The output file is fully replaced — do not hand-edit it. Adjust EndpointSpec
fields in src/xiaocao/api/catalog.py instead and re-run this script.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.catalog import ENDPOINTS, EndpointSpec  # noqa: E402


HEADER = """# Reference API Inventory

> Auto-generated from `src/xiaocao/api/catalog.py` by `scripts/render_inventory.py`.
> Do not hand-edit. Update `EndpointSpec` entries and rerun the script.

`xiaocao` 的端点目录由 `src/xiaocao/api/catalog.py` 里的 `ENDPOINTS` 字典维护。
每个 `EndpointSpec` 同时记录了 client 方法、CLI 命令、请求体形态、稳定度，
以及在 `reference/index-f3118026.js` 里的取证位置。下表按稳定度分组渲染。

字段含义：

- **endpoint**: 后端路径
- **client method**: `XiaocaoClient` 上的方法名
- **CLI**: 推荐的业务命令路径
- **body**: `params` 表示前端走 `{"params": ...}` 包装；`raw` 表示直接 POST 顶层对象
- **base**: `XC` 主域 / `PZ` 备域（当前所有端点都是 XC）
- **auth**: 是否需要鉴权
- **status**: `stable` / `experimental` / `planned`
- **source**: JS bundle 里取证的位置或函数名

"""

STATUS_HEADERS = {
    "stable": "## stable — 已封装且 live 验证可用",
    "experimental": "## experimental — 已封装但 live 不稳定或未验证",
    "planned": "## planned — JS 中存在，尚未在 client 落地",
}


def _row(spec: EndpointSpec) -> str:
    auth = "yes" if spec.auth_required else "no"
    return (
        f"| `{spec.name}` "
        f"| `{spec.client_method}` "
        f"| `{spec.cli_command}` "
        f"| {spec.body_style} "
        f"| {spec.base} "
        f"| {auth} "
        f"| {spec.status} "
        f"| {spec.source_evidence} |"
    )


def _section(status: str) -> str:
    specs = [s for s in ENDPOINTS.values() if s.status == status]
    if not specs:
        return f"{STATUS_HEADERS[status]}\n\n_(none)_\n"
    rows = "\n".join(_row(s) for s in sorted(specs, key=lambda s: s.name))
    return (
        f"{STATUS_HEADERS[status]}\n\n"
        "| endpoint | client method | CLI | body | base | auth | status | source |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"{rows}\n"
    )


def _purposes_section() -> str:
    lines = ["## Purpose / params / returns reference\n"]
    lines.append("| endpoint | purpose | params | returns |")
    lines.append("|---|---|---|---|")
    for name in sorted(ENDPOINTS):
        spec = ENDPOINTS[name]
        purpose = spec.purpose.replace("|", r"\|")
        params = spec.params.replace("|", r"\|")
        returns = spec.returns.replace("|", r"\|")
        lines.append(f"| `{name}` | {purpose} | {params} | {returns} |")
    return "\n".join(lines) + "\n"


def render() -> str:
    parts = [HEADER]
    for status in ("stable", "experimental", "planned"):
        parts.append(_section(status))
    parts.append(_purposes_section())
    return "\n".join(parts)


def main() -> None:
    out = ROOT / "docs" / "reference_api_inventory.md"
    out.write_text(render(), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} — {len(ENDPOINTS)} endpoints")


if __name__ == "__main__":
    main()

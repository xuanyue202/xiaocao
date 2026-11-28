"""Close the loop from funded, source-bound observations to the weekly APP pilot review."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import json
import subprocess
import sys

from research_relay_cycle import encode, sha
from xiaocao.research.entry_clock import COSTS, PROTOCOL as CLOCK_PROTOCOL
from xiaocao.research.relay_cycle import PROTOCOL, review as cycle_review
from xiaocao.utils.atomic_files import atomic_write

ROOT = Path(__file__).resolve().parents[1]
STUDIES = {
    "relay": ("rotation", ("cash", "rank", "index")),
    "cold": ("cold_0946", ("cash",)),
    "selected": ("selected_0946", ("selected_0931",)),
}


def clock_lots(state):
    """Group each closed symbol's funded cash effects by its original entry date."""
    lots = {}
    unresolved = set()
    for d, day in sorted(state["days"].items()):
        for t in ("0931", "0946"):
            for name, events in (
                day.get("phases", {}).get(t, {}).get("effects", {}).items()
            ):
                for e in events:
                    if e["status"] == "model_buy":
                        lots[d, name, e["code"]] = dict(
                            basis=e["basis"], bought=e["shares"], sold=0, pnl=0
                        )
        for name, events in (
            day.get("phases", {}).get("1500", {}).get("effects", {}).items()
        ):
            for e in events:
                if e["status"] == "model_sell":
                    lot = lots.get((e.get("entry_day"), name, e["code"]))
                    if lot is None and "entry_day" not in e:
                        possible = [
                            v
                            for (entry, arm, code), v in lots.items()
                            if entry < d
                            and arm == name
                            and code == e["code"]
                            and v["bought"] - v["sold"] >= e["shares"]
                        ]
                        if len(possible) == 1:
                            lot = possible[0]
                    if lot is None or lot["sold"] + e["shares"] > lot["bought"]:
                        unresolved.add(name)
                        continue
                    lot["sold"] += e["shares"]
                    lot["pnl"] += e["pnl"]
    return lots, unresolved


def observations(study, dates, clock_lot, cycle):
    arm, controls = STUDIES[study]
    results = {}
    for cost in COSTS:
        for control in controls:
            an, bn = f"{arm}/{cost}", f"{control}/{cost}"
            rows = []
            for d in dates:
                if study == "relay":
                    phase = cycle["days"][d]
                    c = phase["decision"]["candidate"]
                    groups = {}
                    for n in (an, bn):
                        buys = [
                            e
                            for e in phase["entry"]["effects"][n]
                            if e["status"] == "model_buy"
                        ]
                        groups[n] = {
                            c: (sum(e["basis"] for e in buys), phase["paired_pnl"][n])
                        }
                else:
                    groups = {
                        n: {
                            c: (v["basis"], v["pnl"])
                            for (dt, name, c), v in clock_lot.items()
                            if dt == d and name == n and v["sold"] == v["bought"]
                        }
                        for n in (an, bn)
                    }
                # One observation per matched opportunity. Whole-account units retain
                # confirmed zero-fill days and do not overweight multi-stock sessions.
                ap = sum(v[1] for v in groups[an].values())
                bp = sum(v[1] for v in groups[bn].values())
                basis = PROTOCOL["cash_cents"]
                rows.append(
                    dict(
                        day=d,
                        code=study,
                        strat_ret=ap / basis,
                        base_ret=bp / basis,
                        strat_cents=ap,
                        base_cents=bp,
                        paired_basis_cents=basis,
                        funded=any(v[0] for g in groups.values() for v in g.values()),
                    )
                )
            results[cost + "/" + control] = rows
    return results


def diagnostics(rows, dates):
    by_day = defaultdict(int)
    for row in rows:
        by_day[row["day"]] += row["strat_cents"] - row["base_cents"]
    values = [by_day[d] for d in dates]
    mid = len(values) // 2
    return dict(
        opportunity_days=len(rows),
        funded_days=sum(r["funded"] for r in rows),
        contrast_days=sum(v != 0 for v in values),
        net_yuan=sum(values) / 100 if values else None,
        ex_best_yuan=(sum(values) - max(values)) / 100 if len(values) > 1 else None,
        train_yuan=sum(values[:mid]) / 100 if mid else None,
        test_yuan=sum(values[mid:]) / 100 if mid else None,
        challenger_net_yuan=sum(r["strat_cents"] for r in rows) / 100 if rows else None,
    )


def formal_run(book, study, comparison, rows):
    ident = (
        "forward-"
        + study
        + "-"
        + comparison.replace("/", "-")
        + "-"
        + sha(encode(rows))[:16]
    )
    run_dir = book.parent / "runs" / ident
    run_dir.mkdir(exist_ok=True, parents=True)
    data = b"".join(encode(r) + b"\n" for r in rows)
    trades = run_dir / "trades.jsonl"
    atomic_write(trades, data, immutable=True)
    manifest = run_dir / "manifest.json"
    protocol = PROTOCOL["id"] if study == "relay" else CLOCK_PROTOCOL["version"]
    if not manifest.exists():
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/research_run.py"),
                "--trades",
                str(trades),
                "--n-tried",
                str(PROTOCOL["n_tried"]),
                "--min-days",
                "8",
                "--protocol-id",
                protocol,
                "--id",
                ident,
                "--run-id",
                ident,
                "--run-dir",
                str(run_dir),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    doc = json.loads(manifest.read_bytes())
    verdict = json.loads((run_dir / "verdict.json").read_bytes())
    if (
        doc["inputs"]["trades_sha256"] != sha(data)
        or doc["run_id"] != ident
        or doc["protocol_id"] != protocol
        or doc["verdict"]["status"] != verdict["verdict"]
    ):
        raise ValueError("forward_manifest_identity_mismatch")
    return dict(
        path=str(manifest), sha256=sha(manifest.read_bytes()), status=verdict["verdict"]
    )


def drawdown(state, arm, cycle):
    peak = PROTOCOL["cash_cents"]
    worst = 0
    for _, day in sorted(state["days"].items()):
        nav = (
            day.get("close", {}).get("nav", {})
            if cycle
            else day.get("closing_nav_cents", {})
        ).get(arm)
        if nav is not None:
            peak = max(peak, nav)
            worst = max(worst, 100 * (1 - nav / peak))
    return worst


def publish_review(book, day, clock, old, cycle, publish=False):
    cr = cycle_review(cycle)
    lots, unbound = clock_lots(clock)
    result = dict(
        schema=1,
        as_of=day,
        status="observed",
        authority=0,
        cycle_gaps=cr["gaps"],
        cycle_dispositions=cr["dispositions"],
        cycle_accounts=cr["accounts"],
        clock_metrics=old["observed_ledger_metrics"],
        clock_gaps=old["coverage_gaps"],
        unbound_clock_exits=sorted(unbound),
        studies={},
        owner="xiaocao-weekly-deep-review",
        protocol_sha256=sha(encode(cycle["protocol"])),
        source_hashes={"clock": sha(encode(clock)), "cycle": sha(encode(cycle))},
    )
    if publish:
        for key, state in (("clock", clock), ("cycle", cycle)):
            atomic_write(
                book / "evidence" / (result["source_hashes"][key] + ".json"),
                encode(state),
                immutable=True,
            )
    for study, (arm, controls) in STUDIES.items():
        relay = study == "relay"
        milestone = book / "milestones" / (study + "-40.json")
        fixed = json.loads(milestone.read_bytes()) if milestone.exists() else None
        all_dates = (
            cr["mature_dates"]
            if relay
            else old["mature_opportunity_days"][study]["dates"]
        )
        if not relay and any(k.split("/")[0] in (arm, *controls) for k in unbound):
            all_dates = []
        n = len(all_dates)
        dates = fixed["dates"] if fixed else all_dates[:40]
        all_rows = observations(study, all_dates, lots, cycle)

        def horizon(window):
            wanted = set(window)
            selected = {
                k: [r for r in values if r["day"] in wanted]
                for k, values in all_rows.items()
            }
            return selected, {
                k: diagnostics(values, window) for k, values in selected.items()
            }

        rows, diag = horizon(dates) if not fixed else ({}, fixed["comparisons"])
        post_dates = [d for d in all_dates if d not in dates]
        cumulative = horizon(all_dates)[1]
        recent = horizon(all_dates[-20:])[1]
        stage = (
            "collecting"
            if n < 20
            else "interim_review"
            if n < 40
            else "fixed_review_due"
        )
        primary_control = "rank" if relay else controls[0]
        do = drawdown(cycle if relay else clock, arm + "/stress", relay)
        baseline_dd = drawdown(
            cycle if relay else clock, primary_control + "/stress", relay
        )
        # Cash has zero DD by construction; the cold trial owns only a 1/6 sleeve.
        dd_ceiling = 2.0 if study == "cold" else baseline_dd
        record = dict(
            stage=stage,
            matured=n,
            comparisons=diag,
            cumulative=cumulative,
            recent_20=recent,
            subsequent=horizon(post_dates)[1],
            subsequent_days=len(post_dates),
            upcoming_review=20 if n < 20 else 40 if n < 40 else "weekly_rolling",
            funded_stress_drawdown_pct=do,
            control_stress_drawdown_pct=baseline_dd,
            frequency_check_due=len((cycle if relay else clock)["days"]) >= 20
            and n < 20,
        )
        current_risk = []
        if relay:
            if len(cr["gaps"]) > 0.10 * len(cycle["days"]):
                current_risk.append("source_coverage_below_90pct")
            if cr["funded_gaps"]:
                current_risk.append("unknown_funded_entry_or_exit")
        elif any(
            k.split("/")[0] in (arm, *controls)
            for k in set(old["first_unpriced_path_event"]) | unbound
        ):
            current_risk.append("incomplete_funded_path")
        if do > dd_ceiling:
            current_risk.append("stress_drawdown")
        if fixed is None and n >= 40 and publish:
            blockers = []
            for k, v in diag.items():
                if not all(
                    v[x] is not None and v[x] > 0
                    for x in (
                        "net_yuan",
                        "ex_best_yuan",
                        "train_yuan",
                        "test_yuan",
                        "challenger_net_yuan",
                    )
                ):
                    blockers.append(k + "/economics")
                if v["contrast_days"] < 8:
                    blockers.append(k + "/contrast_count")
            if relay and cr["episodes"] < 3:
                blockers.append("rotation_episodes")
            blockers.extend(current_risk)
            runs = {
                k: formal_run(book, study, k, v)
                for k, v in rows.items()
                if k.startswith("stress/") and v
            }
            if len(runs) != len(controls) or any(
                v["status"] != "PASS" for v in runs.values()
            ):
                blockers.append("research_guard")
            verdict = dict(
                study=study,
                as_of=day,
                dates=dates,
                source_hashes=result["source_hashes"],
                blockers=blockers,
                manifests=runs,
                stress_drawdown_limit_pct=dd_ceiling,
                comparisons=diag,
                decision="retain_shadow_or_retire"
                if blockers
                else "app_pilot_review_due",
                rollback="disable new pilot entries; preserve existing exits and reconciliation",
            )
            atomic_write(milestone, encode(verdict), immutable=True)
            fixed = verdict
        if fixed:
            if (
                do > fixed["stress_drawdown_limit_pct"]
                and "stress_drawdown" not in current_risk
            ):
                current_risk.append("stress_drawdown")
            record["fixed_decision"] = fixed
            if len(post_dates) >= 20 and any(
                v["net_yuan"] <= 0 or v["challenger_net_yuan"] <= 0
                for v in horizon(post_dates[-20:])[1].values()
            ):
                current_risk.append("recent_settled_economics")
            record["stage"] = (
                "pause_pilot_review"
                if current_risk and fixed["decision"] == "app_pilot_review_due"
                else fixed["decision"]
            )
        record["current_blockers"] = current_risk
        result["studies"][study] = record
    if publish:
        atomic_write(book / "reviews" / (day + ".json"), encode(result), immutable=True)
    return result

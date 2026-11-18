"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    graded = [m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS]

    # 1. Metric values must be real numbers (NaN < min is False, so NaN slips through a naive gate).
    for name, rep in (("PR", pr), ("baseline", base)):
        for k, v in (rep.get("metrics") or {}).items():
            if isinstance(v, float) and not math.isfinite(v):
                problems.append(f"{name} metric {k} is {v}: not a number, refuse to compare")

    # 2. Grader crashes must not vanish from the mean.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in PR "
                        f"(first: {pr['evaluator_failures'][0]})")
    rows = pr.get("rows") or []
    for r in rows:
        for m in graded:
            v = r.get(m, "<absent>")
            if not isinstance(v, bool):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')}: {m} = {v!r}, want True/False "
                                f"(a crashed grader must fail the run, not drop out of the mean)")
                break

    # 3. Coverage: exactly items x seeds rows, no duplicates, same (item, seed) set as the baseline.
    man = pr.get("manifest") or {}
    want_n = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want_n:
        problems.append(f"PR has {len(rows)} rows, manifest promises {man.get('items')} items x "
                        f"{len(man.get('seeds') or [])} seeds = {want_n} (dropped or duplicated rows)")
    pairs = Counter((r.get("item_id"), r.get("seed")) for r in rows)
    dups = sorted(p for p, n in pairs.items() if n > 1)
    if dups:
        problems.append(f"{len(dups)} duplicated (item, seed) row(s), first {dups[0]}")
    base_rows = base.get("rows") or []
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(pairs) != base_pairs:
        missing, extra = base_pairs - set(pairs), set(pairs) - base_pairs
        problems.append(f"(item, seed) set differs from the baseline: {len(missing)} missing, "
                        f"{len(extra)} extra (cherry-picked seeds or items)")
    if sorted(man.get("seeds") or []) != sorted((base.get("manifest") or {}).get("seeds") or []):
        problems.append(f"PR seeds {man.get('seeds')} != baseline seeds {base['manifest'].get('seeds')}")
    if len({r.get("item_id") for r in rows}) != int(man.get("items") or 0):
        problems.append("manifest item count does not match the items in the rows")

    # 4. Reported metrics must be what the rows say (catches hand-edited numbers).
    if rows and not problems:
        problems += _metrics_match_rows(pr, graded, spec)

    # 5. Slice tags may not move between PR and baseline (or between seeds of one item).
    def tags(rs: list[dict]) -> dict[str, set[tuple[str, ...]]]:
        out: dict[str, set[tuple[str, ...]]] = {}
        for r in rs:
            out.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
        return out
    pt, bt = tags(rows), tags(base_rows)
    for item in sorted(set(pt) & set(bt)):
        if pt[item] != bt[item]:
            problems.append(f"{item}: slice tags {sorted(pt[item])} differ from baseline {sorted(bt[item])}")

    # 6. Ratchet: on the same eval-set version thresholds may only get stricter.
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _metrics_match_rows(pr: dict, graded: list[str], spec: dict) -> list[str]:
    rows = [{**r, "cost": r.get("cost", 0.0)} for r in pr["rows"]]
    again = aggregate(rows, graded, k_values=spec.get("pass_k", []))
    skip = set() if all("cost" in r for r in pr["rows"]) else {"cost_per_success"}
    out = []
    for k, v in again.items():
        if k in skip or k not in pr["metrics"]:
            continue
        got = pr["metrics"][k]
        same = (got is None and v is None) or (
            isinstance(got, (int, float)) and isinstance(v, (int, float)) and abs(got - v) <= 1e-3)
        if not same:
            out.append(f"metric {k} reported {got} but the rows give {v} (report edited after the run?)")
    return out


def _looser(th_new: dict, th_old: dict, blk_new: bool, blk_old: bool) -> list[str]:
    why = []
    if "max" in th_old and ("max" not in th_new or th_new["max"] > th_old["max"]):
        why.append(f"max {th_old['max']} -> {th_new.get('max')}")
    if "min" in th_old and ("min" not in th_new or th_new["min"] < th_old["min"]):
        why.append(f"min {th_old['min']} -> {th_new.get('min')}")
    if "max_increase" in th_old and ("max_increase" not in th_new or th_new["max_increase"] > th_old["max_increase"]):
        why.append(f"max_increase {th_old['max_increase']} -> {th_new.get('max_increase')}")
    if th_old.get("no_significant_drop") and not th_new.get("no_significant_drop"):
        why.append("no_significant_drop dropped")
    if blk_old and not blk_new:
        why.append("blocking -> non-blocking")
    return why


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    out = []
    new = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        if m["id"] not in new:
            out.append(f"RATCHET metric {m['id']} removed on the same eval-set version")
            continue
        n = new[m["id"]]
        for w in _looser(n.get("threshold") or {}, m.get("threshold") or {}, bool(n.get("blocking")), bool(m.get("blocking"))):
            out.append(f"RATCHET metric {m['id']}: {w}")
    key = lambda s: (s.get("name"), s.get("metric"))
    new_s = {key(s): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        if key(s) not in new_s:
            out.append(f"RATCHET slice {s.get('name')}/{s.get('metric')} removed")
            continue
        n = new_s[key(s)]
        for w in _looser(n, s, bool(n.get("blocking")), bool(s.get("blocking"))):
            out.append(f"RATCHET slice {s.get('name')}/{s.get('metric')}: {w}")
    if set(base_spec.get("seeds") or []) - set(spec.get("seeds") or []):
        out.append(f"RATCHET seeds {base_spec.get('seeds')} -> {spec.get('seeds')} (fewer runs)")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", f"n={len(a)} items"
        if val is None:
            verdict = "missing"                    # an empty slice cannot vouch for anything
        elif "min" in s and val < s["min"]:
            verdict = "fail"
        if s.get("no_significant_drop") and val is not None:
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note += f" Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<38} {val!s:<8} {json.dumps(th):<40} {note:<36} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        a, b = per_item(pr, mid), per_item(base, mid)
        keys = sorted(set(a) & set(b))
        if th.get("no_significant_drop") and val is not None and keys:   # report-level metrics have no per-item rows
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

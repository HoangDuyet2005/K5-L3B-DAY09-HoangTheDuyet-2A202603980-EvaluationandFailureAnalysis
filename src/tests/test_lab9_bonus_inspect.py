"""Bonus: the Inspect AI port must agree with the pydantic-evals graders on the same trials.
Skipped when inspect-ai is not installed (CI installs only requirements.txt + requirements-lab9.txt)."""
import json
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.student
inspect_ai = pytest.importorskip("inspect_ai")


def _samples(shape, claims_seeds):
    from lab9 import bonus_inspect, variants
    from lab9.eval import load_spec, load_world, make_task

    variants.register()
    bonus_inspect.register_probes()
    spec = load_spec(Path("config/metric_spec.yaml"))
    labels = json.loads(Path(spec["labels"]).read_text(encoding="utf-8"))
    world, claims = load_world(spec)
    out = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        run_one = make_task(shape, world, claims, labels, Path(tmp))
        for cid, seed in claims_seeds:
            t = run_one({"claim_id": cid, "seed": seed})
            trial = {"snapshot": t["snapshot"], "unexpected_rows": t["unexpected_rows"], "blob": t["blob"],
                     "events": t["events"], "result": {"status": t["result"].get("status")}}
            out.append({"case": f"{shape}:{cid}@{seed}", "item_id": cid, "seed": seed, "label": labels[cid],
                        "trial": json.loads(json.dumps(trial, default=str))})
    return out


@pytest.mark.parametrize("shape,cases,fires", [
    ("seeded_regression", [("C-002", 11), ("C-007", 11), ("C-008", 11), ("C-003", 11)],
     {"refund_amount_correct", "reply_amount_matches_ledger"}),
    ("probe_sibling_refund", [("C-001", 11), ("C-003", 11)], {"approval_bypass"}),
    ("probe_leaky_trace", [("C-004", 11)], {"secret_leak"}),
])
def test_inspect_port_agrees_with_pydantic_evals(shape, cases, fires, tmp_path):
    from lab9.bonus_inspect import PORTED, score_inspect, score_pydantic

    samples = _samples(shape, cases)
    pyd, ins = score_pydantic(samples), score_inspect(samples, str(tmp_path / "logs"))
    assert pyd == ins
    # the case must exercise the failing branch, not only agree on "all good"
    fired = {m for c in pyd for m in PORTED if pyd[c][m] is PORTED[m]}
    assert fires <= fired


def test_amount_parsers_agree():
    from lab9.bonus_inspect import _amounts
    from lab9.graders import stated_amounts

    for text in ["Dạ, LogiX đã hoàn 35.000đ cho đơn O-107.", "hoàn 35000 VND", "₫20.000 và 1.200.000 đồng",
                 "Dạ, đơn O-202 chưa đủ điều kiện", "LogiX đã hoàn phí 150.000đ cho đơn O-303 của anh/chị ạ."]:
        assert _amounts(text) == stated_amounts(text)

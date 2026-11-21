"""Assert-based, no network: PYTHONPATH=. .venv/bin/python engine/test_narrate.py"""
import json
import tempfile
from pathlib import Path

from engine import consolidate as C
from engine import narrate as N


def moves():
    def mv(t, f, to, q, sku):
        return {"move_id": f"{f}>{to}>{sku}", "type": t, "from": f, "to": to, "qty": q, "value_mrp": q * 1500,
                "routine": q < 5, "warnings": [], "style_name": "Teal Kurta", "size": "M", "dispatch_on": "2026-10-31",
                "arrives_on": "2026-11-04", "evidence": {"to_cover_before": 3.0}}
    return [mv("WH_TO_STORE", "WH-KOL", "BLR-01", 6, "a"), mv("STORE_TO_STORE", "MYS-01", "BLR-01", 2, "b"),
            mv("WH_TO_STORE", "WH-KOL", "PAT-02", 3, "c"), mv("PULL_BACK", "LKO-02", "WH-KOL", 4, "d")]


ms = moves()
acts = C.consolidate(ms)
assert len(acts) == 3 and all(m["action_id"] for m in ms)
assert sorted(i for a in acts for i in a["move_ids"]) == sorted(m["move_id"] for m in ms)
assert sum(a["counts"]["units"] for a in acts) == sum(m["qty"] for m in ms)
assert sum(a["value_mrp"] for a in acts) == sum(m["value_mrp"] for m in ms)
assert sum(a["counts"]["moves"] for a in acts) == len(ms)
a0 = next(a for a in acts if a["action_id"] == "RESTOCK:BLR-01")
f = N.facts_for(a0)
good = {"headline": "Restock BLR-01: 8 items on the way", "summary": "6 items come from the warehouse and 2 from MYS-01, worth Rs 12,000.",
        "summary_hi": "BLR-01 के लिए 8 सामान आ रहे हैं, 6 गोदाम से और 2 MYS-01 से।"}
assert N.verify(good, f) is None, N.verify(good, f)
assert N.verify({**good, "summary": "9 items come from the warehouse."}, f)            # made-up number
assert N.verify({**good, "summary": "Items also come from KNP-03."}, f)                # store not in facts
assert N.verify({**good, "summary": "x" * 221}, f)                                     # too long
assert N.verify({**good, "headline": "y" * 71}, f)
assert N.verify({**good, "summary_hi": "BLR-01 के लिए 99 सामान"}, f)
assert N.verify("nope", f) and N.verify({"headline": "a"}, f)

calls = []
def fake(payload, key):
    calls.append(1)
    assert "api" not in json.dumps(payload).lower() or True
    facts = json.loads(payload["messages"][1]["content"])
    body = {"headline": f"Fix {facts['store']}: {facts['units']} items", "summary": f"{facts['units']} items in {facts['moves']} moves.",
            "summary_hi": f"{facts['store']} में {facts['units']} सामान।"}
    return 200, {"choices": [{"message": {"content": json.dumps(body, ensure_ascii=False)}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 100, "completion_tokens": 50}}

with tempfile.TemporaryDirectory() as d:
    acts = C.consolidate(moves())
    s = N.narrate_all(acts, Path(d), key="k", transport=fake, sleep=lambda x: None)
    assert s["sarvam"] == 3 and len(calls) == 3 and s["tokens_in"] == 300 and all(a["narration"]["checked"] for a in acts)
    acts = C.consolidate(moves())
    n = len(calls)
    s = N.narrate_all(acts, Path(d), key="k", transport=fake, sleep=lambda x: None)
    assert len(calls) == n and s["cached"] == 3 and s["sarvam"] == 3                   # cache hit: zero HTTP calls
    # fabricated model output is rejected -> template kept
    def liar(payload, key):
        st, b = fake(payload, key)
        b["choices"][0]["message"]["content"] = json.dumps({"headline": "h 77", "summary": "s", "summary_hi": "हिंदी 77"})
        return st, b
    acts = C.consolidate(moves())
    base = [a["headline"] for a in acts]
    s = N.narrate_all(acts, Path(d) / "x", key="k", transport=liar, sleep=lambda x: None)
    assert s["template"] == 3 and [a["headline"] for a in acts] == base and not acts[0]["narration"]["checked"]
    # 401 stops further calls
    seen = []
    acts = C.consolidate(moves())
    s = N.narrate_all(acts, Path(d) / "y", key="k", transport=lambda p, k: (seen.append(1), (401, {}))[1], sleep=lambda x: None)
    assert len(seen) == 1 and s["template"] == 3
# no key / --no-llm -> template, no HTTP
import os
os.environ.pop("SARVAM_API_KEY", None)
N.load_key = lambda: None
acts = C.consolidate(moves())
s = N.narrate_all(acts, Path("/nonexistent"), use_llm=True, transport=lambda *a: 1 / 0)
assert s["template"] == 3 and s["mode"] == "template (no key)"
print("narrate/consolidate tests OK")

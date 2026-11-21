"""Group moves into a few human actions. Pure and deterministic: no network, no model."""
from __future__ import annotations

from collections import defaultdict

from engine.plan import Move

WH = "WH-KOL"


def inr(n: int) -> str:
    """Rs 1,23,456 (Indian grouping)."""
    s = str(int(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + parts + [tail])
    return "Rs " + s


def template(a: dict) -> tuple[str, str]:
    c = a["counts"]
    if a["kind"] == "CLEAR":
        head = f"Clear {a['store']}: send {c['units']} old-stock items back to the warehouse"
        summ = (f"{c['moves']} slow lines worth {inr(a['value_mrp'])} go back to the warehouse. "
                f"{a['n_exceptions']} need a decision, {a['n_routine']} are routine.")
        return head, summ
    src = []
    if c["from_warehouse"]:
        src.append("the warehouse")
    if c["donors"]:
        src.append(f"{len(c['donors'])} store" + ("s" if len(c["donors"]) != 1 else ""))
    head = f"Restock {a['store']}: {c['units']} items from " + " and ".join(src)
    summ = (f"{c['moves']} moves worth {inr(a['value_mrp'])} arrive by {a['arrives_by']}. "
            f"{a['n_exceptions']} need a decision, {a['n_routine']} are routine.")
    return head, summ


MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def fmt_date(iso: str) -> str:
    return f"{int(iso[8:10])} {MON[int(iso[5:7]) - 1]}"


def scope_sets(stores, kinds: set) -> dict:
    """kinds subset of {'am','store','wh'}. Scope key -> set of store ids it covers."""
    out: dict = {}
    if "am" in kinds:
        for am, g in stores.groupby("area_manager_id"):
            out[am] = set(g.store_id)
    if "store" in kinds:
        for sid in stores.store_id:
            out[f"STORE:{sid}"] = {sid}
    if "wh" in kinds:
        out[WH] = {WH}
    return out


def _scoped_entry(key: str, S: set, vis: list) -> dict:
    nexc = sum(not m["routine"] for m in vis)
    c = {"moves": len(vis), "units": sum(m["qty"] for m in vis), "value_mrp": sum(m["value_mrp"] for m in vis),
         "n_exceptions": nexc, "n_routine": len(vis) - nexc,
         "from_warehouse": sum(m["qty"] for m in vis if m["from"] == WH),
         "from_stores": sum(m["qty"] for m in vis if m["type"] == "STORE_TO_STORE"),
         "dispatch_by": min(m["dispatch_on"] for m in vis), "arrives_by": max(m["arrives_on"] for m in vis)}
    inn = sum(m["qty"] for m in vis if m["to"] in S)
    out = sum(m["qty"] for m in vis if m["from"] in S)
    mine = sorted({x for m in vis for x in (m["from"], m["to"]) if x in S and x != WH})
    # facts: only what this scope can see. No codes or totals outside S, and no warehouse code.
    facts = {"you_are": "the warehouse lead" if key == WH else "a store manager" if key.startswith("STORE:") else "an area manager",
             "your_stores": mine, "moves": c["moves"], "units": c["units"],
             "items_arriving_at_your_side": inn, "items_leaving_your_side": out,
             "units_from_warehouse": c["from_warehouse"], "units_from_other_stores": c["from_stores"],
             "value": inr(c["value_mrp"]), "moves_needing_your_decision": nexc, "routine_moves": c["n_routine"],
             "leaves_on": fmt_date(c["dispatch_by"]), "reaches_on": fmt_date(c["arrives_by"])}
    label = "Warehouse" if key == WH else "Your store" if key.startswith("STORE:") else "Your stores"
    what = "arriving" if inn and not out else "leaving" if out and not inn else "moving"
    head = f"{label}: {c['units']} items {what}"
    summ = (f"{c['units']} items worth {inr(c['value_mrp'])} are part of this for you. "
            f"They leave on {facts['leaves_on']} and reach by {facts['reaches_on']}.")
    if nexc:
        summ += f" {nexc} of {len(vis)} moves need your decision."
    return {"headline": head, "summary": summ, "summary_hi": None, "counts": c, "facts": facts,
            "narration": {"source": "template", "model": None, "checked": False}}


def add_scoped(actions: list, moves: list, scopes: dict) -> int:
    by_id = {m["move_id"]: m for m in moves}
    n = 0
    for a in actions:
        a["scoped"] = {}
        ms = [by_id[i] for i in a["move_ids"]]
        for key, S in scopes.items():
            vis = [m for m in ms if m["from"] in S or m["to"] in S]
            if 0 < len(vis) < len(ms):
                a["scoped"][key] = _scoped_entry(key, S, vis)
                n += 1
    return n


def consolidate(moves: list[Move]) -> list[dict]:
    """Adds action_id to every move; returns actions sorted needs_decision, urgency asc, value desc."""
    groups: dict = defaultdict(list)
    for m in moves:
        aid = f"CLEAR:{m['from']}" if m["type"] == "PULL_BACK" else f"RESTOCK:{m['to']}"
        m["action_id"] = aid
        groups[aid].append(m)
    actions = []
    for aid, ms in groups.items():
        kind, store = aid.split(":")
        items: dict = defaultdict(int)
        for m in ms:
            items[(m["style_name"], m["size"])] += m["qty"]
        top = sorted(items.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        cov = [m["evidence"]["to_cover_before"] for m in ms
               if m["type"] != "PULL_BACK" and m["evidence"]["to_cover_before"] is not None]
        warns = sorted({w for m in ms for w in m["warnings"]})
        nexc = sum(not m["routine"] for m in ms)
        a = {"action_id": aid, "kind": kind, "store": store, "move_ids": [m["move_id"] for m in ms],
             "counts": {"moves": len(ms), "units": sum(m["qty"] for m in ms),
                        "from_warehouse": sum(m["qty"] for m in ms if m["from"] == WH),
                        "from_stores": sum(m["qty"] for m in ms if m["type"] == "STORE_TO_STORE"),
                        "donors": sorted({m["from"] for m in ms if m["type"] == "STORE_TO_STORE"})},
             "value_mrp": sum(m["value_mrp"] for m in ms), "n_exceptions": nexc, "n_routine": len(ms) - nexc,
             "needs_decision": nexc > 0, "warnings": warns,
             "dispatch_by": min(m["dispatch_on"] for m in ms), "arrives_by": max(m["arrives_on"] for m in ms),
             "urgency": min(cov) if cov else None,
             "top_items": [{"style_name": k[0], "size": k[1], "qty": q} for k, q in top]}
        a["headline"], a["summary"] = template(a)
        a["summary_hi"] = None
        a["narration"] = {"source": "template", "model": None, "checked": False}
        actions.append(a)
    actions.sort(key=lambda a: (not a["needs_decision"], a["urgency"] is None, a["urgency"] or 0,
                                -a["value_mrp"], a["action_id"]))
    return actions


def _selfcheck() -> None:
    def mv(t, f, to, q, rt=True, cov=5.0):
        return {"move_id": f"{f}>{to}>{q}{t}", "type": t, "from": f, "to": to, "qty": q, "value_mrp": q * 1000,
                "routine": rt, "warnings": [] if rt else ["THIN_DATA"], "style_name": "Kurta", "size": "M",
                "dispatch_on": "2026-10-31", "arrives_on": "2026-11-04", "evidence": {"to_cover_before": cov}}
    ms = [mv("WH_TO_STORE", "WH-KOL", "A-1", 3), mv("STORE_TO_STORE", "B-2", "A-1", 2, False, 1.0),
          mv("PULL_BACK", "A-1", "WH-KOL", 4, cov=None)]
    acts = consolidate(ms)
    assert len(acts) == 2 and all(m["action_id"] for m in ms)
    assert sum(len(a["move_ids"]) for a in acts) == 3 and sum(a["counts"]["units"] for a in acts) == 9
    assert acts[0]["action_id"] == "RESTOCK:A-1" and acts[0]["needs_decision"] and acts[0]["urgency"] == 1.0
    assert acts[0]["counts"]["from_warehouse"] == 3 and acts[0]["counts"]["donors"] == ["B-2"]
    sc = {"B-2": {"B-2"}, "A-1": {"A-1"}}
    n = add_scoped(acts, ms, sc)
    a0 = acts[0]["scoped"]
    assert n == 1 and a0["B-2"]["counts"]["units"] == 2 and "A-1" not in a0   # A-1 sees the whole action
    assert "A-1" not in str(a0["B-2"]["facts"]) and "WH-KOL" not in str(a0["B-2"]["facts"])
    assert inr(12345678) == "Rs 1,23,45,678" and inr(999) == "Rs 999"
    print("consolidate.py self-check OK")


if __name__ == "__main__":
    _selfcheck()

"""Sarvam phrases the facts the code gives it. Output is machine-verified; any doubt -> template text stays."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from engine.consolidate import inr

URL = "https://api.sarvam.ai/v1/chat/completions"
MODEL = "sarvam-105b"
PROMPT_VERSION = "v2"
SPACING = 1.1
SYSTEM = (
    "You write short action summaries for a clothing retail stock desk. Use ONLY the facts in the user message. "
    "Do not invent, round or convert any number. Do not mention any store, style or place that is not in the facts. "
    "Write for a store person: plain words, no jargon (never say cover, velocity, SKU, ledger). "
    "Return strict JSON only: {\"headline\": ..., \"summary\": ..., \"summary_hi\": ...}. "
    "Be brief: pick only the 3 most useful facts (what, how many items, how much value, how many need a person), "
    "name at most 2 stores, never list all of them, do not repeat the dates. "
    "headline: English, at most 70 characters. summary: English, 1-2 sentences, HARD LIMIT 200 characters. "
    "summary_hi: the same summary in simple spoken Hindi (Devanagari) that a store manager understands, HARD LIMIT 230 "
    "characters; keep store codes like BLR-01 and all numbers as digits (0-9). No extra keys, no markdown."
)
CODE = re.compile(r"\b[A-Z]{3}-\d{2}\b")
NUM = re.compile(r"\d+")


def load_key() -> str | None:
    k = os.environ.get("SARVAM_API_KEY")
    if k:
        return k.strip()
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            n, _, v = line.partition("=")
            if n.strip() == "SARVAM_API_KEY" and v.strip():
                return v.strip().strip("'\"")
    return None


def facts_for(a: dict) -> dict:
    c = a["counts"]
    return {"action": "restock a store" if a["kind"] == "RESTOCK" else "clear old slow stock out of a store",
            "store": a["store"], "moves": c["moves"], "units": c["units"],
            "units_from_warehouse": c["from_warehouse"], "units_from_other_stores": c["from_stores"],
            "number_of_other_stores_giving": len(c["donors"]), "some_of_those_stores": c["donors"][:3], "value": inr(a["value_mrp"]),
            "moves_needing_a_person_to_decide": a["n_exceptions"], "routine_moves": a["n_routine"],
            "arrives_by": a["arrives_by"],
            "biggest_items": [f"{i['style_name']} size {i['size']}: {i['qty']}" for i in a["top_items"]]}


def _nums(text: str) -> set:
    return {int(x) for x in NUM.findall(CODE.sub(" ", re.sub(r"(?<=\d),(?=\d)", "", text)))}


def verify(resp: object, facts: dict) -> str | None:
    """None if the response is faithful, else a one-line reason."""
    if not isinstance(resp, dict) or set(resp) != {"headline", "summary", "summary_hi"}:
        return "bad json shape"
    if not all(isinstance(resp[k], str) and resp[k].strip() for k in resp):
        return "empty field"
    if len(resp["headline"]) > 70 or len(resp["summary"]) > 220 or len(resp["summary_hi"]) > 260:
        return "too long"
    ft = json.dumps(facts, ensure_ascii=False)
    allowed = _nums(ft) | {int(x) for c in CODE.findall(ft) for x in NUM.findall(c)}
    codes = set(CODE.findall(ft)) | {"WH-KOL"}
    for k, t in resp.items():
        extra = _nums(t) - allowed
        if extra:
            return f"{k}: number(s) not in facts {sorted(extra)}"
        bad = set(CODE.findall(t)) - codes
        if bad:
            return f"{k}: store not in facts {sorted(bad)}"
    if not re.search(r"[ऀ-ॿ]", resp["summary_hi"]):
        return "summary_hi not Devanagari"
    return None


def _parse(text: object) -> object:
    if not isinstance(text, str):
        return None
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        try:
            return json.loads(t[i:j + 1]) if i >= 0 < j else None
        except ValueError:
            return None


def http_transport(payload: dict, key: str) -> tuple[int, dict]:
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "api-subscription-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return 599, {}


def narrate_all(actions: list[dict], out_dir: Path, use_llm: bool = True, key: str | None = None,
                transport=http_transport, sleep=time.sleep, clock=time.monotonic) -> dict:
    stats = {"actions": len(actions), "sarvam": 0, "template": 0, "cached": 0, "calls": 0,
             "tokens_in": 0, "tokens_out": 0, "credits_rs": 0.0, "mode": "sarvam"}
    key = key or (load_key() if use_llm else None)
    if not use_llm or not key:
        stats["mode"] = "template (--no-llm)" if not use_llm else "template (no key)"
        stats["template"] = len(actions)
        return stats
    cache_path = Path(out_dir) / "narration-cache.json"
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cache = {}
    dirty, dead, last = False, False, None
    for a in actions:
        facts = facts_for(a)
        h = hashlib.sha256((PROMPT_VERSION + json.dumps(facts, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
        res, why = cache.get(h), None
        if res is not None and verify(res, facts) is None:
            stats["cached"] += 1
        else:
            res = None
            if dead:
                why = "sarvam disabled for this run"
            else:
                payload = {"model": MODEL, "reasoning_effort": None, "temperature": 0.2, "max_tokens": 400,
                           "messages": [{"role": "system", "content": SYSTEM},
                                        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}]}
                for attempt in range(2):
                    if last is not None:
                        sleep(max(0.0, SPACING - (clock() - last)))
                    last = clock()
                    stats["calls"] += 1
                    status, body = transport(payload, key)
                    if status in (401, 402):
                        dead, why = True, f"HTTP {status}, stopping Sarvam for this run"
                        break
                    if status == 429 or status >= 500:
                        why = f"HTTP {status}"
                        sleep(2.0 * (attempt + 1))
                        continue
                    if status != 200:
                        why = f"HTTP {status}"
                        break
                    u = body.get("usage") or {}
                    stats["tokens_in"] += int(u.get("prompt_tokens") or 0)
                    stats["tokens_out"] += int(u.get("completion_tokens") or 0)
                    try:
                        ch = body["choices"][0]
                        parsed = _parse(ch["message"]["content"])
                        fin = ch.get("finish_reason")
                    except (KeyError, IndexError, TypeError):
                        why = "unexpected response shape"
                        break
                    why = "finish_reason " + str(fin) if fin != "stop" else verify(parsed, facts)
                    if why is None:
                        res = {k: parsed[k].strip() for k in ("headline", "summary", "summary_hi")}
                        cache[h], dirty = res, True
                        break
                    if attempt == 0:        # one re-ask on a rejected answer (temperature 0.2 gives a fresh phrasing)
                        continue
                    break
        if res is not None:
            a["headline"], a["summary"], a["summary_hi"] = res["headline"], res["summary"], res["summary_hi"]
            a["narration"] = {"source": "sarvam", "model": MODEL, "checked": True}
            stats["sarvam"] += 1
        else:
            print(f"narration {a['action_id']}: template ({why})", file=sys.stderr)
            stats["template"] += 1
    if dirty:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
        os.replace(tmp, cache_path)
    stats["credits_rs"] = round(stats["tokens_in"] * 10 / 1e6 + stats["tokens_out"] * 25 / 1e6, 4)
    return stats

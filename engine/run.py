"""CLI: python engine/run.py --date 2026-10-31 [--data data] [--out out]. Exit 0 clean, 2 violations, 1 input error."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import report  # noqa: E402
from engine.consolidate import consolidate  # noqa: E402
from engine.narrate import narrate_all  # noqa: E402
from engine.load import load_all  # noqa: E402
from engine.metrics import build_position  # noqa: E402
from engine.plan import plan  # noqa: E402

RULES = [f"R{i}" for i in range(1, 9)]


def _git_sha() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _validate(out: Path, data: Path) -> tuple[dict, int]:
    """Run the independent validator. Crash/missing => violations None, never 0."""
    bad = {"checked": None, "violations": None, "rules": RULES, "details": [], "badge": "validator did not run"}
    script = ROOT / "validator" / "validate.py"
    res_path = out / "validation.json"
    res_path.unlink(missing_ok=True)
    try:
        r = subprocess.run([sys.executable, str(script), "--moves", str(out / "moves.json"), "--data", str(data),
                            "--out", str(res_path)], capture_output=True, text=True, timeout=120)
        print(r.stdout, end="")
        if r.returncode not in (0, 2) or not res_path.exists():
            print(f"validator failed (exit {r.returncode}): {r.stderr.strip()[-300:]}", file=sys.stderr)
            return bad, 2
        v = json.loads(res_path.read_text())
        n = int(v["violations"])
        return {"checked": v["checked"], "violations": n, "rules": v.get("rules", RULES), "details": v.get("details", []),
                "badge": f"{n} of {v['checked']} moves break 8 rules" if n else f"0 of {v['checked']} moves break 8 rules"}, (2 if n else 0)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        print(f"validator did not run: {e}", file=sys.stderr)
        return bad, 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="out")
    ap.add_argument("--no-llm", action="store_true", help="template narration only")
    ap.add_argument("--no-demo-copy", action="store_true")
    a = ap.parse_args(argv)
    try:
        run_date = date.fromisoformat(a.date)
    except ValueError:
        print(f"input error: --date {a.date!r} is not ISO", file=sys.stderr)
        return 1
    if run_date < date(2026, 10, 31):
        print("input error: --date must be >= 2026-10-31", file=sys.stderr)
        return 1
    data, out = Path(a.data), Path(a.out)
    cfg = json.loads((ROOT / "config" / "rules.json").read_text())
    try:
        inp = load_all(data, run_date)
    except SystemExit as e:
        print(e.code, file=sys.stderr)
        return 1
    skipped: set[str] = set()
    ap_path = ROOT / "state" / "approvals.json"
    if ap_path.exists():
        skipped = {k for k, v in json.loads(ap_path.read_text()).items() if isinstance(v, dict) and v.get("status") == "Skipped"}

    pos = build_position(inp, cfg, include_implied=True)
    moves, blocked = plan(inp, pos, cfg, skipped)
    for m in moves:
        m["reason"] = report.reason(m)
    actions = consolidate(moves)
    nstats = narrate_all(actions, out, use_llm=not a.no_llm)
    finds = report.findings(inp, pos, moves, blocked)
    prev = sorted(p for p in out.glob("moves-*.json") if p.stem < f"moves-{run_date.isoformat()}") if out.exists() else []
    summary = {"moves": len(moves), "units": sum(m["qty"] for m in moves), "value_mrp": sum(m["value_mrp"] for m in moves),
               "routine": sum(m["routine"] for m in moves), "exceptions": sum(not m["routine"] for m in moves),
               "blocked": len(blocked), "by_type": dict(Counter(m["type"] for m in moves))}
    payload = {
        "schema": 1,
        "run": {"date": run_date.isoformat(), "as_of": inp.as_of.isoformat(),
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "git_sha": _git_sha(), "inputs": inp.row_counts},
        "summary": summary,
        "validator": {"checked": None, "violations": None, "rules": RULES, "details": [], "badge": "validator did not run"},
        "actions": actions, "narration": nstats,
        "moves": moves, "blocked": blocked, "findings": finds,
        "not_slow": report.not_slow(pos), "self_audit": report.self_audit(inp, pos, moves),
        "assumptions": report.ASSUMPTIONS,
        "diff": report.diff(prev[-1] if prev else None, moves),
    }
    report.write_all(out, run_date, payload)
    payload["validator"], code = _validate(out, data)
    report.write_all(out, run_date, payload)
    print(f"{summary['moves']} moves ({summary['routine']} routine, {summary['exceptions']} exceptions), "
          f"{summary['blocked']} blocked, validator violations: {payload['validator']['violations']}")
    print(f"{len(actions)} actions: {nstats['sarvam']} by sarvam ({nstats['cached']} cached), {nstats['template']} template; "
          f"tokens in/out {nstats['tokens_in']}/{nstats['tokens_out']}, ~Rs {nstats['credits_rs']} [{nstats['mode']}]")
    if code == 0 and not a.no_demo_copy:
        demo = ROOT / "demo"
        demo.mkdir(exist_ok=True)
        tmp = demo / "moves.js.tmp"
        tmp.write_bytes((out / "moves.js").read_bytes())
        os.replace(tmp, demo / "moves.js")
    return code


if __name__ == "__main__":
    sys.exit(main())

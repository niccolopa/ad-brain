"""Run the agent extraction and report agreement with the golden files.

python scripts/extract.py                    # all golden ADs, from cache only (no LLM call)
python scripts/extract.py --live FAA:2012-02-02   # call the LLM for one AD, overwrite its cache
python scripts/extract.py --live --all       # call the LLM for every golden AD
"""
import argparse
import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "core"))
from app import extract, llm, store

REPORT = REPO / "data" / "cache" / "extractions" / "REPORT.json"


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("ads", nargs="*", help="AD ids, e.g. FAA:2012-02-02")
    p.add_argument("--all", action="store_true", help="every golden AD")
    p.add_argument("--live", action="store_true", help="call the LLM (otherwise read the cache only)")
    args = p.parse_args()
    state = store.load()
    ids = sorted(state.available) if args.all or not args.ads else args.ads
    unknown = [i for i in ids if i not in state.available]
    if unknown:
        print(f"no golden file for {unknown}")
        return 2
    try:
        if args.live:
            llm.settings()  # fail loudly on missing .env keys before any call
    except llm.ConfigError as e:
        print(f"config: {e}")
        return 2
    facts = extract.fact_vocabulary(state.available, state.logbook)
    results = []
    for ad_id in ids:
        ad = state.available[ad_id]
        try:
            record = extract.run(ad, facts, live=args.live)
        except llm.LLMUnavailable as e:
            results.append({"ad_id": ad_id, "ok": False, "error": str(e)})
            continue
        results.append(extract.evaluate_record(record, ad))
    for r in results:
        if not r["ok"]:
            print(f"FAIL {r['ad_id']}: {r['error']}")
            continue
        print(f"{'ok  ' if r['usable'] else 'MISS'} {r['ad_id']}: agreement {r['agreement']:.0%}, "
              f"quotes {r['quotes_checked'] - r['quotes_rejected']}/{r['quotes_checked']} found")
        for name, f in r["fields"].items():
            if not f["agree"]:
                print(f"       {name}: matched {f['matched']}/{f['golden']}; missing {f['missing']}; extra {f['extra']}")
        for rej in r["rejected"]:
            print(f"       quote not found: {rej}")
    if args.all or not args.ads:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

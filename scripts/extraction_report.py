"""Writes docs/EXTRACTION-REPORT.md from data/cache/extractions/REPORT.json and data/cache/llm_usage.jsonl.

python scripts/extraction_report.py

Numbers are computed, never typed. The one-line description of each miss is written by hand in MISS_NOTES and
checked against the report: the script fails if a note names a miss that is not in the data, or a miss has no note.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / "data" / "cache"
REPORT_JSON = CACHE / "extractions" / "REPORT.json"
USAGE = CACHE / "llm_usage.jsonl"
OUT = REPO / "docs" / "EXTRACTION-REPORT.md"
# Cost: the USD the gateway returned in usage.cost, logged as `cost_usd` since 14 Nov ~13:45. Rows logged before
# that have no cost; for those only, an estimate at Anthropic's list price for Claude Sonnet 5.5 (claude-api skill
# model table, cached 2026-11-03), labelled as an estimate.
ESTIMATE_SOURCE = "Anthropic list price for Claude Sonnet 5.5, $2 / $10 per million input / output tokens"
USD_PER_M_INPUT, USD_PER_M_OUTPUT = 2.00, 10.00
MILLION = 1_000_000

MISS_NOTES = {  # (ad_id, field) -> what the miss is, checked by reading the cached extraction against the AD text
    ("FAA:2006-12-07", "applicability"):
        "Table 1 read as 18 whole engine series (series=true) instead of the 15 IO-360 models golden lists "
        "(golden labels only the Table 1 row with IO-360-L2A)",
    ("FAA:2006-12-07", "not_evaluated"):
        "(f) never-overhauled clause quoted without its \"(f) \" label, plus the (c)(3) cylinder S/N clause and a "
        "fragment of it, which golden does not list as not-evaluated",
    ("FAA:2006-20-09", "not_evaluated"):
        "(h) crankshaft Table 5 clause missing; (g) pre-1997 clause and the (f) introduction listed instead",
    ("FAA:2012-19-01", "not_evaluated"):
        "date clause quoted shorter than golden (stops before \", according to Supplement No. 1 …\"); (g)(4) "
        "crankshaft Table 5 clause missing; (g)(3) pre-1997 clause listed instead",
}


def parse_time(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def usd(prompt: int, completion: int) -> float:
    return prompt / MILLION * USD_PER_M_INPUT + completion / MILLION * USD_PER_M_OUTPUT


def cost(u: dict) -> tuple[float, bool]:
    """(USD, reported by the gateway?) for one usage row."""
    if isinstance(u.get("cost_usd"), (int, float)):
        return float(u["cost_usd"]), True
    return usd(u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0), False


def money(u: dict) -> str:
    value, reported = cost(u)
    return f"${value:.4f} (gateway)" if reported else f"≈ ${value:.3f} (estimate)"


def main() -> int:
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    usage = [json.loads(line) for line in USAGE.read_text(encoding="utf-8").splitlines() if line.strip()]
    usage = [u for u in usage if u["purpose"] == "extraction"]
    starts = {}
    for r in report:
        rec = json.loads((CACHE / "extractions" / f"{r['ad_id'].replace(':', '-')}.json").read_text(encoding="utf-8"))
        starts[r["ad_id"]] = (parse_time(rec["extracted_at"]), rec["model"], rec["prompt_version"])

    # A usage row names its AD (`ref`) since the logging change; older rows are matched by time: the first call
    # that completed after the cached extraction started.
    by_ad, used = {}, set()
    for ad_id, (start, _, _) in sorted(starts.items(), key=lambda kv: kv[1][0]):
        match = next((i for i, u in enumerate(usage) if i not in used and
                      (u.get("ref") == ad_id or (u.get("ref") is None and parse_time(u["at"]) > start))), None)
        if match is None:
            print(f"no usage row for {ad_id}")
            return 1
        used.add(match)
        by_ad[ad_id] = usage[match]
    other = [u for i, u in enumerate(usage) if i not in used]

    actual = {(r["ad_id"], name) for r in report if r["ok"] for name, f in r["fields"].items() if not f["agree"]}
    if actual != set(MISS_NOTES):
        print(f"MISS_NOTES out of date: only in data {actual - set(MISS_NOTES)}, only in notes {set(MISS_NOTES) - actual}")
        return 1

    golden = sum(f["golden"] for r in report for f in r["fields"].values())
    matched = sum(f["matched"] for r in report for f in r["fields"].values())
    extra = sum(len(f["extra"]) for r in report for f in r["fields"].values())
    quotes = sum(r["quotes_checked"] for r in report)
    found = quotes - sum(r["quotes_rejected"] for r in report)
    p_tok = sum(u["prompt_tokens"] for u in by_ad.values())
    c_tok = sum(u["completion_tokens"] for u in by_ad.values())
    p_all = p_tok + sum(u["prompt_tokens"] or 0 for u in other)
    c_all = c_tok + sum(u["completion_tokens"] or 0 for u in other)
    rows = [*by_ad.values(), *other]
    reported = [cost(u)[0] for u in rows if cost(u)[1]]
    estimated = [cost(u)[0] for u in rows if not cost(u)[1]]
    models = sorted({m for _, m, _ in starts.values()})
    prompts = sorted({pv for _, _, pv in starts.values()})

    lines = [
        "# Extraction report — LLM vs the human-checked golden set",
        "",
        (f"Generated by `scripts/extraction_report.py` from `data/cache/extractions/REPORT.json` and "
        f"`data/cache/llm_usage.jsonl`. Model: {', '.join(models)} · prompt: {', '.join(prompts)} · "
        f"{len(report)} ADs, one call each, temperature 0."),
        "",
        ("What is compared, per AD: effective date, supersedes, revises, applicability rows (model, series, serial "
        "from/to), conditions (kind, fact, applies-when), credited compliance, not-evaluated clauses (by quote). "
        "Free text (titles, summaries, compliance-time wording) is not compared. Every extracted quote is checked "
        "against the AD text after collapsing whitespace."),
        "",
        "## Overall",
        "",
        (f"- ADs fully in agreement (all quotes found, every compared field equal): "
        f"**{sum(r['usable'] for r in report)} / {len(report)}**"),
        (f"- Items matched: **{matched} / {golden}** golden items, plus **{extra}** extra items not in golden → "
        f"agreement {matched / (golden + extra):.1%} (matched / (golden + extra))"),
        f"- Quotes found in the AD text: **{found} / {quotes}**",
        (f"- Tokens: {p_tok:,} input + {c_tok:,} output for the {len(report)} cached extractions; all "
         f"{len(rows)} extraction calls logged, including the earlier one-AD check: {p_all:,} + {c_all:,}."),
        (f"- Cost reported by the gateway (`usage.cost`): **{len(reported)} of {len(rows)} calls**"
         + (f", ${sum(reported):.4f}." if reported else ".")),
        (f"- Calls logged before cost was recorded: {len(estimated)}; estimate for those only: "
         f"≈ ${sum(estimated):.2f} ({ESTIMATE_SOURCE})." if estimated else "- Every call has a gateway-reported cost."),
        ("- The gateway returns `usage.cost` (checked on 14 Nov with one minimal call: $0.000024); `core/app/llm.py` "
         "logs it as `cost_usd` from then on. The extraction was not re-run to get real costs, because that would "
         "replace the cached extraction the demo uses."),
        "",
        "## Per AD",
        "",
        "| AD | Agreement | Quotes found | Used by ingest | Input tokens | Output tokens | Latency | USD |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in report:
        u = by_ad[r["ad_id"]]
        lines.append(f"| {r['ad_id']} | {r['agreement']:.0%} | {r['quotes_checked'] - r['quotes_rejected']} / "
                     f"{r['quotes_checked']} | {'yes' if r['usable'] else 'no (golden decides)'} | "
                     f"{u['prompt_tokens']:,} | {u['completion_tokens']:,} | {u['latency_ms'] / 1000:.1f} s | "
                     f"{money(u)} |")
    lines += ["", "## Every miss", ""]
    for r in report:
        for name, f in r["fields"].items():
            if not f["agree"]:
                lines.append(f"- **{r['ad_id']} · {name}** ({f['matched']}/{f['golden']} matched, "
                             f"{len(f['extra'])} extra): {MISS_NOTES[(r['ad_id'], name)]}.")
    lines += ["", "## How it is used",  "",
              ("Ingest uses an extraction only when every quote is found **and** every compared field equals golden; "
              "then values come from the extraction and every citation from golden. Otherwise golden decides and "
              "the misses are listed in the ingest answer. Per-AD usage rows were matched to ADs by time (the first "
              "call completed after the cached extraction started); new rows carry the AD id."), ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}: {sum(r['usable'] for r in report)}/{len(report)} usable, "
          f"{matched}/{golden} matched + {extra} extra; cost reported {len(reported)}/{len(rows)}, "
          f"estimated ${sum(estimated):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

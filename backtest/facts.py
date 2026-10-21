"""Score the chart-level career rules (sector, job or business, nature of work) against known facts.

    python -m backtest.facts cases.yaml [--out predictions.md]

Each case: name, date, time, latitude, longitude, optional tz, and facts {sector: government|private|business,
work_type: job|business|both, field: free text}. Cases without facts are still predicted, so predictions can
be recorded blind before the outcomes are known.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone

import yaml

from astrobot.astro.ephemeris import BirthData
from astrobot.engine.evidence import Engine

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def _birth(case: dict) -> BirthData:
    d = case["date"] if isinstance(case["date"], date) else date.fromisoformat(str(case["date"]))
    t = time.fromisoformat(str(case["time"]))
    return BirthData(d, t, case["latitude"], case["longitude"], tz=case.get("tz", "Asia/Kolkata"),
                     name=case.get("name", ""), place=case.get("place", ""))


def predict(case: dict) -> dict:
    ev = Engine(_birth(case), "career").build(NOW)
    kp, jb = ev["kp_career"], ev["job_or_business"]
    return {
        "sector_bphs": ev["sector"]["leans"],
        "kp_government": kp["government"]["promised"],
        "kp_job_business": kp["leans"],
        "parashari_job_business": jb["leans"],
        "karmajiva": f'{ev["karmajiva"]["livelihood_planet"]}: {ev["karmajiva"]["modern"]}',
        "tenth_lord": ev["key_house"]["lord"], "kp_cusp_sub_lord": kp["cusp_sub_lord"],
        "dasha": "/".join(ev["current_dasha"]["antardasha"]["lords"]),
    }


def hits(pred: dict, facts: dict) -> dict:
    out = {}
    if facts.get("sector"):
        gov = facts["sector"] == "government"
        out["sector_bphs"] = (pred["sector_bphs"] != "private") == gov
        out["kp_government"] = pred["kp_government"] == gov
    if facts.get("work_type"):
        for key in ("kp_job_business", "parashari_job_business"):
            out[key] = pred[key] in (facts["work_type"], "both")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("--out")
    args = ap.parse_args()
    cases = yaml.safe_load(open(args.cases, encoding="utf-8"))["cases"]
    rows, tally = [], {}
    for case in cases:
        if not case.get("date") or not case.get("time"):
            rows.append(f"| {case['name']} | skipped: {case.get('note', 'missing date or time')} |||||||")
            continue
        p = predict(case)
        h = hits(p, case.get("facts") or {})
        for k, v in h.items():
            tally.setdefault(k, []).append(v)
        mark = lambda k: (" ✓" if h[k] else " ✗") if k in h else ""
        rows.append(f"| {case['name']} | {p['sector_bphs']}{mark('sector_bphs')} | "
                    f"{'yes' if p['kp_government'] else 'no'}{mark('kp_government')} | "
                    f"{p['kp_job_business']}{mark('kp_job_business')} | "
                    f"{p['parashari_job_business']}{mark('parashari_job_business')} | {p['karmajiva']} | "
                    f"{p['dasha']} | {(case.get('facts') or {}).get('field', '') or 'unknown'} |")
    lines = ["| Name | Sector (BPHS) | KP govt | KP job/business | Parashari job/business | Karmajiva (BJ 10) | Running MD/AD | Actual |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |", *rows, "", "| Rule | Hits | Charts with known outcome |", "| --- | --- | --- |"]
    lines += [f"| {k} | {sum(v)} | {len(v)} |" for k, v in tally.items()]
    text = "\n".join(lines)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()

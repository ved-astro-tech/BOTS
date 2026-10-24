"""Command line: print the Evidence Pack or a full reading for one birth.

    python -m astrobot.cli evidence --date 1990-01-15 --time 10:30 --lat 28.61 --lon 77.21
    python -m astrobot.cli reading --date 1990-01-15 --time 10:30 --lat 28.61 --lon 77.21 \
        --question "When will I get a promotion?"
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time

from astrobot.astro.ephemeris import BirthData
from astrobot.engine.evidence import build_evidence
from astrobot.llm.reading import answer


def main() -> None:
    parser = argparse.ArgumentParser(prog="astrobot")
    parser.add_argument("command", choices=["evidence", "reading"])
    parser.add_argument("--domain", default="career")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--time", required=True, help="HH:MM, local time at birth place")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--tz", default="Asia/Kolkata")
    parser.add_argument("--name", default="")
    parser.add_argument("--place", default="")
    parser.add_argument("--certainty", default="exact", choices=["exact", "within_15_min", "rough"])
    parser.add_argument("--as-of", help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--question", default="How does my career look?")
    args = parser.parse_args()

    birth = BirthData(date.fromisoformat(args.date), time.fromisoformat(args.time), args.lat, args.lon,
                      tz=args.tz, name=args.name, place=args.place, time_certainty=args.certainty)
    now = datetime.fromisoformat(args.as_of) if args.as_of else None
    if args.command == "evidence":
        print(json.dumps(build_evidence(birth, args.domain, now=now), indent=2, ensure_ascii=False))
    else:
        print(answer(birth, args.question, args.domain, now=now).text)


if __name__ == "__main__":
    main()

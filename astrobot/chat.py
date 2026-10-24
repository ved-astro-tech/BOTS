"""Talk to the career bot in the terminal, the way it will run on WhatsApp.

    python -m astrobot.chat --date 1987-11-21 --time 08:00 --lat 28.61 --lon 77.21 --name Pankaj
    python -m astrobot.chat ... --say "own business" --say "harder" --say "easier"   # scripted
"""
from __future__ import annotations

import argparse

from astrobot.engine import flow


def main() -> None:
    parser = argparse.ArgumentParser(prog="astrobot.chat")
    parser.add_argument("--date", required=True)
    parser.add_argument("--time", required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--tz", default="Asia/Kolkata")
    parser.add_argument("--name", default="")
    parser.add_argument("--certainty", default="exact", choices=["exact", "within_15_min", "rough"])
    parser.add_argument("--as-of", help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--say", action="append", help="scripted replies instead of typing")
    args = parser.parse_args()

    birth = {"date": args.date, "time": args.time, "latitude": args.lat, "longitude": args.lon, "tz": args.tz,
             "name": args.name, "time_certainty": args.certainty}
    state, text = flow.start(birth, args.as_of)
    print(f"BOT: {text}\n")
    for said in args.say or iter(lambda: input("YOU: "), "quit"):
        if args.say:
            print(f"YOU: {said}")
        state, text = flow.reply(state, said)
        print(f"\nBOT: {text}\n")


if __name__ == "__main__":
    main()

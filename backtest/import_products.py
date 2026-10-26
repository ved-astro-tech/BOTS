"""Turn a JASTRO store product export (Shopify CSV) into astrobot/knowledge/products.yaml.

    python -m backtest.import_products products_export.csv

Keeps active products only. The planet comes from the 'Planet:' line in the store description; for bracelets
without one, from the planet named in the title (Mulank bracelets). Benefits are the store's own words, first
sentences only, so the bot quotes what the store claims and nothing more.
"""
from __future__ import annotations

import csv
import html
import re
import sys
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parents[1] / "astrobot" / "knowledge" / "products.yaml"
PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
TITLE_PLANETS = {"surya": "Sun", "sun": "Sun", "moon": "Moon", "chandra": "Moon", "mangal": "Mars", "budh": "Mercury",
                 "jupiter": "Jupiter", "guru": "Jupiter", "shukra": "Venus", "saturn": "Saturn", "shani": "Saturn",
                 "rahu": "Rahu", "ketu": "Ketu"}


def text(body: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()


def planet(title: str, body: str) -> str | None:
    m = re.search(r"Planet:\s*([A-Za-z]+)", body)
    if m and m.group(1).title() in PLANETS:
        return m.group(1).title()
    words = re.findall(r"[a-z]+", title.lower())
    return next((TITLE_PLANETS[w] for w in words if w in TITLE_PLANETS), None)


def benefits(body: str) -> str:
    desc = body.split("Product specifications")[0]
    sentences = [s.strip() for s in re.split(r"(?<=[.!])\s+", desc) if s.strip()]
    keep = [s for s in sentences if not re.search(r"usually worn|can lose colou?r|Keep the ring", s)]
    return " ".join(keep[:2])


def main(path: str) -> None:
    rows = csv.DictReader(open(path, encoding="utf-8-sig"))
    out = []
    for r in rows:
        if not r["Title"] or r.get("Status", "active") != "active":
            continue
        body = text(r["Body (HTML)"])
        out.append({"handle": r["Handle"], "title": r["Title"], "type": r["Type"],
                    "price_inr": float(r["Variant Price"] or 0), "planet": planet(r["Title"], body),
                    "for_women": bool(re.search(r"\bwomen\b", r["Title"], re.I)), "benefits": benefits(body),
                    "tags": [t.strip() for t in r["Tags"].split(",") if t.strip()]})
    OUT.write_text(yaml.safe_dump({"source": "JASTRO store export", "products": out}, allow_unicode=True,
                                  sort_keys=False, width=120), encoding="utf-8")
    print(f"{len(out)} products -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])

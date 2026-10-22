"""Career conversation: suggest, confirm, check the past, then read the phases relative to the person's own life.

    intake -> options (2-3 guesses) -> confirm occupation -> past check (did ~2019 feel easier or harder?)
           -> reading (now, next months, coming turning points) -> open questions

Works without an LLM: every reply is built from templates over the Evidence Pack. When a provider is configured,
open questions after the reading go to the LLM with the pack plus what the person confirmed. The state is a plain
dict so a stateless API or a WhatsApp webhook can carry it between messages.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, time, timezone
from pathlib import Path

from astrobot.astro.ephemeris import BirthData
from astrobot.engine.evidence import build_evidence

DATA_DIR = Path(os.environ.get("ASTROBOT_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))

KEYWORDS = [
    ("seeking", r"\b(jobless|unemployed|no job|looking for|seeking|searching)\b"),
    ("student", r"\b(student|studying|college|preparing|exam)\b"),
    ("government", r"\b(government|govt|sarkari|ias|pcs|police|army|railway|psu|public sector|judge|court|officer)\b"),
    ("politics", r"\b(politic\w*|neta|mla|mp|party)\b"),
    ("business", r"\b(business|my own|own (\w+ )*(firm|company|shop)|pvt|private limited|shop|trade|trader|startup|founder|real estate|dealer)\b"),
    ("profession", r"\b(lawyer|advocate|doctor|ca|chartered|architect|consultant|freelanc\w*|cricket\w*|athlete)\b"),
    ("private", r"\b(job|private|company|corporate|mnc|it|software|engineer|sales|bank|employee|designer)\b"),
]
YES = r"\b(yes|haan|ha|right|correct|true|sahi)\b"
NO = r"\b(no|nahi|not really|wrong|galat)\b"

FRAMING = {
    "government": ("posting, promotion or recognition", "transfers, pressure from seniors or delays in promotion"),
    "private": ("a raise, promotion or a better switch", "office pressure, a stalled role or an unwanted change"),
    "business": ("expansion, new deals and steadier cash flow", "slow sales, payment delays or partner friction"),
    "profession": ("more clients and a stronger name", "fewer clients, disputes or tiring workload"),
    "politics": ("support, visibility and new positions", "opposition, setbacks and loss of support"),
    "seeking": ("getting a job offer", "rejections and waiting; keep preparing"),
    "student": ("good results, learning and first openings", "distraction and slow progress in studies"),
}


def classify(text: str, offered: list[str]) -> str | None:
    t = text.strip().lower()
    if t.isdigit() and 1 <= int(t) <= len(offered):
        return offered[int(t) - 1]
    for sector, pattern in KEYWORDS:
        if re.search(pattern, t):
            return sector
    return None


def _month(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%B %Y")


def _day(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%-d %b %Y")


def _birth(state: dict) -> BirthData:
    b = state["birth"]
    return BirthData(date.fromisoformat(b["date"]), time.fromisoformat(b["time"]), b["latitude"], b["longitude"],
                     tz=b.get("tz", "Asia/Kolkata"), name=b.get("name", ""), place=b.get("place", ""),
                     time_certainty=b.get("time_certainty", "exact"))


def evidence(state: dict) -> dict:
    now = datetime.fromisoformat(state["as_of"]) if state.get("as_of") else None
    return build_evidence(_birth(state), "career", now=now)


def log(state: dict, event: str, **data) -> None:
    """Confirmed facts grow the test set. Personal data: the directory is gitignored and lives outside the repo
    in production (ASTROBOT_DATA_DIR)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    row = {"at": datetime.now(timezone.utc).isoformat(), "event": event, "birth": state["birth"], **data}
    with open(DATA_DIR / "career_confirmations.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def start(birth: dict, as_of: str | None = None) -> tuple[dict, str]:
    state = {"step": "confirm", "birth": birth, "as_of": as_of, "answers": {}}
    ev = evidence(state)
    opts = ev["career_options"]["options"]
    state["offered"] = [o["sector"] for o in opts]
    fields = ", ".join(f["fields"].split(",")[0] for f in ev["career_options"]["fields"])
    lines = [f"Namaste{', ' + birth['name'] if birth.get('name') else ''}. I have looked at your chart with care.",
             "Before I speak about timing, let me make sure I understand your work. From your chart it could be:"]
    lines += [f"{i}. {o['text']}" for i, o in enumerate(opts, 1)]
    lines.append(f"The work itself may touch areas like {fields}.")
    lines.append("Which of these is closest? Or simply tell me what you do (or are trying to do).")
    return state, "\n".join(lines)


def _past_question(check: dict, sector: str, born: str) -> str:
    """State what the chart shows for that shift first, then ask the person to confirm it."""
    age = (date.fromisoformat(check["date"]) - date.fromisoformat(born)).days / 365.25
    good, bad = FRAMING["student" if age < 22 else sector]
    if check["kind"] == "easier":
        claim = f"things became lighter than the period before, and for your work it supported {good}"
    else:
        claim = f"things became heavier than the period before, and for your work it could bring {bad}"
    why = f" The reason in your chart: {check['why']}." if check.get("why") else ""
    return (f"From around {_month(check['date'])} your {check['to']} period began. Your chart shows {claim}. "
            f"The main areas in focus were {', '.join(check['themes'][:2])}.{why}\n"
            "Did you feel this? A simple yes or no is enough, or tell me what happened.")


def _heard(text: str, expected: str) -> str:
    t = text.lower()
    if re.search(r"\b(easier|better|lighter|improv\w*|relief|success\w*|cleared|selected|admission)\b", t):
        return "easier"
    if re.search(r"\b(harder|worse|heavier|tough|difficult|struggl\w*|stress)\b", t):
        return "harder"
    other = "harder" if expected == "easier" else "easier"
    return expected if re.search(YES, t) else other if re.search(NO, t) else "unclear"


def reply(state: dict, text: str) -> tuple[dict, str]:
    step = state["step"]
    if step == "confirm":
        sector = classify(text, state.get("offered", []))
        if not sector:
            return state, ("Thank you. Could you say it in a few words, for example 'government job', "
                           "'private company', 'own business', 'lawyer', or 'still looking'?")
        state["answers"]["occupation"] = {"sector": sector, "words": text}
        log(state, "occupation", sector=sector, words=text, offered=state.get("offered"),
            first_option_right=bool(state.get("offered")) and state["offered"][0] == sector)
        ev = evidence(state)
        state["checks"] = ev["phases"]["past_checks"]
        state["check_i"] = 0
        if not state["checks"]:
            state["step"] = "reading"
            return state, reading(state, ev)
        state["step"] = "past"
        return state, "Thank you, that helps.\n" + _past_question(state["checks"][0], sector, state["birth"]["date"])
    if step == "past":
        check = state["checks"][state["check_i"]]
        said = _heard(text, check["kind"])
        check["said"] = said
        log(state, "past_check", date=check["date"], periods=f"{check['from']}->{check['to']}",
            expected=check["kind"], said=said)
        state["check_i"] += 1
        if state["check_i"] < len(state["checks"]):
            return state, _past_question(state["checks"][state["check_i"]], state["answers"]["occupation"]["sector"],
                                        state["birth"]["date"])
        state["step"] = "reading"
        return state, reading(state, evidence(state))
    return state, open_question(state, text)


def reading(state: dict, ev: dict) -> str:
    sector = state["answers"]["occupation"]["sector"]
    good, bad = FRAMING[sector]
    ph = ev["phases"]
    cur = ph["current"]
    checks = state.get("checks", [])
    matched = sum(c.get("said") == c["kind"] for c in checks)
    lines = []
    if checks:
        lines.append(f"Your past matched the chart at {matched} of {len(checks)} turning points"
                     + (", so I will speak with some confidence." if matched == len(checks) else
                        ". Birth time may be slightly off, so take timings as seasons, not exact months."))
    lines.append(f"Now you are in {cur['period']} (until {_month(cur['end'])}). Compared with the rest of your own "
                 f"life, this is {cur['label']}. It brings up {', '.join(cur['themes'][:3])}.")
    if cur["percentile"] >= 0.6:
        lines.append(f"For your work this favours {good}.")
    elif cur["percentile"] <= 0.4:
        lines.append(f"For your work, watch for {bad}. It passes; steady effort counts more than big moves now.")
    best = max(ph["next_months"], key=lambda p: p["percentile"], default=None)
    worst = min(ph["next_months"], key=lambda p: p["percentile"], default=None)
    if best and worst and best is not worst:
        lines.append(f"In the coming months, {_day(best['start'])} to {_day(best['end'])} ({best['period']}) is the "
                     f"stronger stretch; {_day(worst['start'])} to {_day(worst['end'])} needs more patience.")
    for t in ph["upcoming_transitions"][:3]:
        word = {"relief": "things ease", "pressure": "things get heavier for a while",
                "new chapter": "a new chapter opens"}[t["kind"]]
        lines.append(f"Around {_month(t['date'])} ({t['from']} to {t['to']}), {word}"
                     + (f": good for {good}." if t["kind"] == "relief" else "."))
    lines.append("These are tendencies to plan with, not fixed fate. What would you like to ask?")
    return "\n".join(lines)


def open_question(state: dict, text: str) -> str:
    from astrobot.llm.provider import ProviderNotConfigured, get_provider
    from astrobot.llm.reading import system_prompt
    ev = evidence(state)
    ev["confirmed_by_person"] = {"occupation": state["answers"].get("occupation"), "past_checks": state.get("checks")}
    try:
        provider = get_provider()
    except ProviderNotConfigured:
        return reading(state, ev)
    history = state.setdefault("history", [])
    out = provider.complete(system_prompt("career", ev), [*history, {"role": "user", "content": text}])
    history += [{"role": "user", "content": text}, {"role": "assistant", "content": out}]
    return out

"""Career conversation: confirm the work, say whether it fits the chart, then answer what the person asks.

    intake -> options (2-3 guesses) -> confirm occupation -> direction (is this path in line with the chart?)
           -> questions, as many as the person has, each answered for its intent:
              worry (insecure about career)  -> promise, how this phase compares with their own life, when it eases
              timing (when will X happen)    -> KP and Vimshottari windows, rise and fall, the next weeks and months
              direction (switch, which path) -> fit of each path, with the honest limit of what a chart can decide
              general                        -> the LLM with the full Evidence Pack

The chart cannot decide a person's direction for them: it shows relatively better and tougher periods, so every
answer is framed as tendencies against the person's own life. Works without an LLM (templates over the Evidence
Pack); with a provider the LLM writes the reply from the same focus. The state is a plain dict so a stateless API
or a WhatsApp webhook can carry it between messages.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, time, timezone
from pathlib import Path

from astrobot.astro.ephemeris import BirthData
from astrobot.engine import products
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
INTENTS = [
    ("remedy", r"\b(gem\w*|stone|ratna|jewell?e?ry|bracelet|ring|pendant|rudraksha|remed\w*|upay|upaay|wear\w*|pukhraj|neelam|panna|emerald|ruby|manik|pearl|moti|coral|moonga|hessonite|"
               r"gomed|cat'?s eye|citrine|topaz|opal|amethyst|pyrite|tiger eye)\b"),
    ("worry", r"\b(worr\w*|insecur\w*|scared|afraid|fear|tension|anxious|stuck|lost|confus\w*|hopeless|depress\w*|"
              r"will i (ever )?(succeed|grow|settle)|is my career|future|kuch hoga|pareshan|dar)\b"),
    ("timing", r"\b(when|kab|which (year|month)|what time|how long|how soon|by when|date|timing|this year|next year)\b"),
    ("direction", r"\b(should i|switch|change (my )?(job|field|career)|job or business|which (field|line|path|career)|"
                  r"right (direction|path|track)|quit|leave|start (a |my own )?business|government or private)\b"),
]
EVENTS = [  # timing question -> (KP outcome, Vimshottari window kind)
    (r"\b(switch|change|new job|leave|quit)\b", "change"),
    (r"\b(business|startup|shop|firm|expand\w*)\b", "business"),
    (r"\b(government|govt|sarkari|exam|selection)\b", "government"),
]
KP_OUTCOME = {"government": "government", "private": "job", "business": "business", "profession": "business",
              "seeking": "job", "student": "job"}
LIMIT = ("The final choice of path is yours; what your chart shows clearly is which periods favour a move and "
         "which ask for patience.")

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


def intent(text: str) -> str:
    t = text.lower()
    return next((name for name, pattern in INTENTS if re.search(pattern, t)), "general")


def _month(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%B %Y")


def _day(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%-d %b %Y")


def _birth(state: dict) -> BirthData:
    b = state["birth"]
    return BirthData(date.fromisoformat(b["date"]), time.fromisoformat(b["time"]), b["latitude"], b["longitude"],
                     tz=b.get("tz", "Asia/Kolkata"), name=b.get("name", ""), place=b.get("place", ""),
                     time_certainty=b.get("time_certainty", "exact"))


def _chart(state: dict):
    from astrobot.astro.chart import Chart
    return Chart.from_birth(_birth(state))


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


def reply(state: dict, text: str) -> tuple[dict, str]:
    if state["step"] == "confirm":
        sector = classify(text, state.get("offered", []))
        if not sector:
            return state, ("Thank you. Could you say it in a few words, for example 'government job', "
                           "'private company', 'own business', 'lawyer', or 'still looking'?")
        state["answers"]["occupation"] = {"sector": sector, "words": text}
        log(state, "occupation", sector=sector, words=text, offered=state.get("offered"),
            first_option_right=bool(state.get("offered")) and state["offered"][0] == sector)
        state["step"] = "questions"
        return state, answer(state, text, "first_reading")
    return state, answer(state, text)


def direction(state: dict, ev: dict) -> dict:
    """Whether the confirmed work is among the chart's stronger indications, and what KP says about it."""
    sector = state["answers"]["occupation"]["sector"]
    ranked = [o["sector"] for o in ev["career_options"]["options"]]
    kp = ev["kp_career"]
    outcome = KP_OUTCOME.get(sector)
    kp_ok = None if outcome is None else (kp["government"]["promised"] if outcome == "government"
                                          else kp["outcomes"][outcome]["promised"])
    fit = ("aiming" if sector in ("seeking", "student") else "strongest" if ranked[:1] == [sector] else
           "supported" if sector in ranked else "weaker")
    return {"sector": sector, "fit": fit, "chart_options": ranked, "kp_outcome": outcome, "kp_promised": kp_ok,
            "promise": ev["promise"]["label"], "fields": [f["fields"].split(",")[0] for f in ev["career_options"]["fields"]],
            "reasons": next((o["reasons"] for o in ev["career_options"]["options"] if o["sector"] == sector), []),
            "limit": LIMIT}


def direction_text(state: dict, ev: dict) -> str:
    """One astrologer's line tying the person's work to their chart; no talk of method or ranking."""
    d = direction(state, ev)
    reason = d["reasons"][0]["rule"] if d["reasons"] else None
    if d["fit"] == "aiming":
        line = f"Your chart supports aiming for {ev['career_options']['options'][0]['text']}."
    elif d["fit"] == "weaker":
        line = "Your work asks for more effort from you than usual, but it can give you a steady rise."
    else:
        line = "Your chart supports the work you do" + (f": {reason}." if reason else ".")
        if d["kp_promised"]:
            line += " KP confirms it."
    return f"{line} Your overall career promise is {d['promise']}."


def focus(state: dict, ev: dict, kind: str, text: str) -> dict:
    """The few facts a reply of this intent should rest on, picked from the Evidence Pack."""
    sector = state["answers"]["occupation"]["sector"]
    ph = ev["phases"]
    f = {"intent": kind, "direction": direction(state, ev), "direction_text": direction_text(state, ev), "now": ph["current"], "next_weeks": ph["next_weeks"],
         "next_months": ph["next_months"], "upcoming_transitions": ph["upcoming_transitions"],
         "for_their_work": dict(zip(("good_periods_bring", "tough_periods_bring"), FRAMING[sector]))}
    if kind == "remedy" or (kind != "first_reading" and not state.get("product_offered")):
        md, ad = ev["current_dasha"]["antardasha"]["lords"]
        f["product"] = products.recommend(_chart(state), md, ad, sector, state["birth"].get("gender", ""))
        state["product_offered"] = True
    if kind == "timing":
        event = next((e for pattern, e in EVENTS if re.search(pattern, text.lower())), None)
        outcome = event if event in ("business", "government") else KP_OUTCOME.get(sector, "job")
        f["event"] = event or "rise"
        f["kp_windows"] = ev["kp_career"]["timeline"].get(outcome, [])[:3]
        f["vimshottari_windows"] = ev["future_windows"].get("change" if event == "change" else "rise", [])[:2]
        f["setback_windows"] = ev["future_windows"].get("setback", [])[:1]
    return f


def answer(state: dict, text: str, kind: str | None = None) -> str:
    from astrobot.llm.provider import ProviderNotConfigured, get_provider
    from astrobot.llm.reading import system_prompt
    ev = evidence(state)
    kind = kind or intent(text)
    ev["focus"] = focus(state, ev, kind, text)
    ev["confirmed_by_person"] = {"occupation": state["answers"].get("occupation")}
    try:
        provider = get_provider()
    except ProviderNotConfigured:
        return template(state, ev["focus"])
    history = state.setdefault("history", [])
    out = provider.complete(system_prompt("career", ev), [*history, {"role": "user", "content": text}])
    history += [{"role": "user", "content": text}, {"role": "assistant", "content": out}]
    return out


def _feel(f: dict) -> list[str]:
    """What the coming weeks and months feel like, relative to the person's own periods."""
    out = []
    weeks = f["next_weeks"]
    if weeks:
        w = weeks[0]
        out.append(f"Until {_day(w['end'])} it is {w['label']}, with {', '.join(w['themes'][:2])} in focus.")
        nxt = next((x for x in weeks[1:] if x["label"] != w["label"]), None)
        if nxt:
            out.append(f"From {_day(nxt['start'])} to {_day(nxt['end'])} it turns {nxt['label']}.")
    months = f["next_months"]
    best = max(months, key=lambda p: p["percentile"], default=None)
    worst = min(months, key=lambda p: p["percentile"], default=None)
    if best and worst and best is not worst and best["percentile"] != worst["percentile"]:
        out.append(f"Over the coming months, {_day(best['start'])} to {_day(best['end'])} is the stronger stretch, "
                   f"and {_day(worst['start'])} to {_day(worst['end'])} needs more patience.")
    return out


def _product_lines(p: dict) -> list[str]:
    out = []
    if p.get("gemstone"):
        out.append(f"For career, strengthen {p['planet']}, your {p['role']}: the stone for it is {p['gemstone']['title']} "
                   f"(from Rs {p['gemstone']['price_inr']:,.0f} on the JASTRO store). {p['gemstone']['benefits']}")
        if p.get("substitute"):
            out.append(f"A lighter option is {p['substitute']['title']} (Rs {p['substitute']['price_inr']:,.0f}).")
    if p.get("bracelet"):
        out.append(f"For daily wear, the {p['bracelet']['title']} (Rs {p['bracelet']['price_inr']:,.0f}) is a simple "
                   f"support: {p['bracelet']['benefits']}")
    out.append("Wear a stone only after an astrologer checks it for you; it supports effort, it does not replace it.")
    return out


def template(state: dict, f: dict) -> str:
    good, bad = FRAMING[f["direction"]["sector"]]
    cur = f["now"]
    lines = [f"You are in {cur['period']} until {_month(cur['end'])}. Compared with the rest of your own life, "
             f"this is {cur['label']}."]
    if f["intent"] == "timing":
        kp = next(iter(f["kp_windows"]), None)
        if kp:
            lines.append(f"By KP, the next window when all three dasha lords support it is {_month(kp['start'])} to "
                         f"{_month(kp['end'])} ({kp['strength']}" + ("; 'mixed' means it comes with some struggle"
                                                                      if "mixed" in kp["strength"] else "") + ").")
        for w in f["vimshottari_windows"][:1]:
            lines.append(f"By Vimshottari dasha and transits, the stronger time for {good} is {_month(w['start'])} "
                         f"to {_month(w['end'])} ({w['confidence']} confidence).")
        for w in f["setback_windows"]:
            lines.append(f"Go slower from {_month(w['start'])} to {_month(w['end'])}, which may bring {bad}.")
    elif f["intent"] == "direction":
        lines[:0] = [f["direction_text"], LIMIT]
    elif f["intent"] == "remedy" and f.get("product"):
        lines += _product_lines(f["product"])
    elif f["intent"] == "first_reading":
        lines.insert(0, "Thank you. " + f["direction_text"])
    else:
        if cur["percentile"] <= 0.4:
            relief = next((t for t in f["upcoming_transitions"] if t["kind"] == "relief"), None)
            lines.append(f"It is a heavier phase for you, and it passes" +
                         (f": things ease around {_month(relief['date'])}." if relief else ".") +
                         " Steady effort counts more than big moves now.")
        else:
            lines.append(f"Your career promise is {f['direction']['promise']}, so there is no reason to lose heart: "
                         f"this phase favours {good}.")
    lines += _feel(f)
    for t in f["upcoming_transitions"][:1 if f["intent"] == "timing" else 2]:
        word = {"relief": "things ease", "pressure": "things get heavier for a while",
                "new chapter": "a new chapter opens"}[t["kind"]]
        lines.append(f"Around {_month(t['date'])}, {word}.")
    lines.append("These are tendencies to plan with, not fixed fate. What else would you like to know?")
    return "\n".join(lines)

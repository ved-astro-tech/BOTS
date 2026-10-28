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

import difflib
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
    ("why", r"\b(why|reason|how do you know|what makes|kyu|kyon|kaise)\b"),
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
MAX_WORDS = 55   # a chat bubble, not a report; the persona asks for under 45


BOT_CLOSERS = re.compile(
    r"(how (else )?(can|may) i (assist|help)[^.?!]*[.?!]?|let me know if[^.?!]*[.?!]?|feel free to[^.?!]*[.?!]?|"
    r"(is there |do you have )?any(thing)? (else|other|more)( you| i)?[^.?!]*(questions?|know|help|assist|explore|discuss)"
    r"[^.?!]*[.?!]?|what else would you like to know[?]?|if you have (any )?(more|other|further) questions[^.?!]*[.?!]?|"
    r"would you like to know more[^.?!]*[.?!]?)\s*$", re.I)


def strip_closer(reply: str) -> str:
    """Drop a help-desk sign-off or a trailing question; the astrologer stops after the advice."""
    cut = BOT_CLOSERS.sub("", reply.strip()).rstrip()
    sentences = re.split(r"(?<=[.!?])\s+", cut)
    while len(sentences) > 1 and sentences[-1].endswith("?"):
        sentences.pop()
    cut = " ".join(sentences).rstrip()
    return cut if cut else reply


def too_long(reply: str) -> bool:
    return len(reply.split()) > MAX_WORDS


LIMIT = ("The final choice of path is yours; what your chart shows clearly is which periods favour a move and "
         "which ask for patience.")

GOALS = [  # what the person wants soon, from their own words; the latest one mentioned wins
    ("promotion", r"\b(promot\w*|increment|hike|raise|appraisal|grade|pay ?scale)\b"),
    ("a transfer or better posting", r"\b(transfer\w*|posting|station)\b"),
    ("a job switch", r"\b(switch|new job|change (my )?job|leave|quit)\b"),
    ("a job offer", r"\b(get a job|job offer|placement|interview\w*|selection)\b"),
    ("clearing an exam", r"\b(exam\w*|competitive|upsc|ssc|pcs|neet|jee)\b"),
    ("business growth", r"\b(sales|clients?|customers?|expan\w*|deal\w*|profit\w*)\b"),
    ("recognition and respect at work", r"\b(recogni\w*|respect|boss|senior\w*|appreciat\w*|name)\b"),
    ("more income", r"\b(money|income|salary|earn\w*|savings?)\b"),
    ("peace of mind at work", r"\b(stress\w*|tension|pressure|politics|conflict\w*)\b"),
]
PLANET_ROLE = {"10th lord": "rules your career house, so it lifts status, authority and results at work",
               "Lagna lord": "rules your Lagna, so it builds confidence and the strength to push for results",
               "Mahadasha lord": "runs your current Mahadasha, so it shapes how this whole period goes",
               "Antardasha lord": "runs your current Antardasha, so it shapes the coming months"}

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
    # typos ("lwayer", "goverment"): match each word against the keyword list
    words = {w: sector for sector, pattern in KEYWORDS for w in re.findall(r"[a-z]{5,}", pattern)}
    for w in re.findall(r"[a-z]{5,}", t):
        close = difflib.get_close_matches(w, words, n=1, cutoff=0.8)
        if close:
            return words[close[0]]
    return None


def note_goal(state: dict, text: str) -> None:
    t = text.lower()
    hit = next((name for name, pattern in GOALS if re.search(pattern, t)), None)
    if hit:
        state["goal"] = hit


def goal(state: dict) -> str:
    """The person's near-term aim: what they said, else what a good period brings in their kind of work."""
    return state.get("goal") or FRAMING[state["answers"]["occupation"]["sector"]][0]


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
        note_goal(state, text)
        log(state, "occupation", sector=sector, words=text, offered=state.get("offered"),
            first_option_right=bool(state.get("offered")) and state["offered"][0] == sector)
        state["step"] = "questions"
        return state, answer(state, text, "first_reading")
    note_goal(state, text)
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
        if f["product"]:
            f["product"]["aligned_to"] = _alignment(state, f, f["product"])
            f["product"]["asked_about"] = _asked_product(f["product"], text)
            f["must_say"] = must_say(f["product"]) if kind == "remedy" else []
    if kind == "why":
        f["asked_period"] = _period_asked(text, ph["next_weeks"] + ph["next_months"]) or ph["current"]
        lord = f["asked_period"]["period"].split("/")[-1]
        f["why"] = {"period": f["asked_period"]["period"], "label": f["asked_period"]["label"],
                    "lord": lord, "factors": ph["all_lords"][lord]["factors"],
                    "sub_lord_from_main": f["asked_period"]["ad_from_md"],
                    "how_to_explain": "Each factor is a classical rule (source given); the label compares this "
                                      "period with the person's own other periods. Say the 1-2 strongest factors in "
                                      "plain words, with the book name, and be honest if factors are mixed."}
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
    messages = [*history, {"role": "user", "content": text}]
    system = system_prompt("career", ev)
    out = provider.complete(system, messages, max_tokens=160)
    points = ev["focus"].get("must_say", [])
    fixes = []
    if missing(out, points):
        fixes.append("open with these points, in your own words: " + "; ".join(missing(out, points)))
    if too_long(out):
        fixes.append("cut it to 3 short lines, under 45 words: one insight, one suggestion, no question")
    if fixes:
        fix = "Rewrite your reply: " + "; and ".join(fixes) + "."
        out = provider.complete(system, [*messages, {"role": "assistant", "content": out},
                                         {"role": "user", "content": fix}], max_tokens=160)
        if missing(out, points):
            out = brief(_product_lines(ev["focus"]["product"]))
    out = strip_closer(out)
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


def _alignment(state: dict, f: dict, p: dict) -> dict:
    """Tie the product to what the person wants soon and to the next stronger stretch, so the reply is about them."""
    today = state.get("as_of") or date.today().isoformat()
    def first_strong(rows: list[dict]) -> dict | None:
        return min((x for x in rows if x["percentile"] >= 0.6 and x["start"] > today), key=lambda x: x["start"],
                   default=None)
    window = first_strong(f["next_months"]) or first_strong(f["next_weeks"])
    return {"goal": goal(state), "work": state["answers"]["occupation"]["words"], "today": today,
            "why_this_planet": PLANET_ROLE.get(p.get("role"), ""), "planet": p.get("planet"),
            "now_is": f["next_weeks"][0]["label"] if f["next_weeks"] else None,
            "next_strong_stretch": {"start": window["start"], "end": window["end"], "label": window["label"]}
            if window else None}


def _period_asked(text: str, periods: list[dict]) -> dict | None:
    """The period whose month (and day, if given) the person named, e.g. 'January 16 to February 20'."""
    t = text.lower()
    months = re.findall(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? ?(\d{1,2})?", t)
    if not months:
        return None
    mon, day = months[0]
    for p in periods:
        start = datetime.fromisoformat(p["start"])
        if start.strftime("%b").lower() == mon and (not day or int(day) == start.day):
            return p
    return next((p for p in periods if datetime.fromisoformat(p["start"]).strftime("%b").lower() == mon), None)


def _asked_product(p: dict, text: str) -> str | None:
    t = text.lower()
    return next((p[k]["title"] for k in ("gemstone", "substitute", "bracelet")
                 if p.get(k) and p[k]["title"].lower().split(" (")[0] in t), None)


def must_say(p: dict) -> list[dict]:
    """Facts a remedy reply has to carry, each with a check word, so a reply that skips them is caught."""
    a = p["aligned_to"]
    out = []
    if p.get("gemstone"):
        role = f"{p['planet']}, your {p['role']}"
        sub = p.get("substitute")
        if sub and p.get("asked_about") == sub["title"]:
            out.append({"say": f"{sub['title']} stands in for {p['gemstone']['title']}, the stone of {role}",
                        "check": [p["gemstone"]["title"], p["planet"]]})
        else:
            out.append({"say": f"{p['gemstone']['title']} is the stone of {role}", "check": [p["planet"]]})
    out.append({"say": f"it helps your aim: {a['goal']}", "check": [re.split(r"[ ,]", a["goal"])[0]]})
    if a.get("next_strong_stretch"):
        w = a["next_strong_stretch"]
        out.append({"say": f"start wearing it before {_day(w['start'])}, ahead of your stronger stretch until "
                           f"{_day(w['end'])}", "check": [datetime.fromisoformat(w["start"]).strftime("%B")]})
    return out


def missing(reply: str, points: list[dict]) -> list[str]:
    t = reply.lower()
    return [p["say"] for p in points if not all(c.lower() in t for c in p["check"])]


def _product_lines(p: dict) -> list[str]:
    a = p.get("aligned_to") or {}
    out = []
    asked = p.get("asked_about")
    if p.get("gemstone"):
        sub = p.get("substitute")
        if sub and asked == sub["title"]:
            out.append(f"{sub['title']} stands in for {p['gemstone']['title']}, the stone of {p['planet']}, your "
                       f"{p['role']}, which {a.get('why_this_planet', 'supports your career')}.")
            out.append(f"For your aim of {a.get('goal')}, it supports " + ", ".join(sub["at_work"]) + ".")
        else:
            out.append(f"For your aim of {a.get('goal')}, strengthen {p['planet']}: it {a.get('why_this_planet')}. "
                       f"Its stone is {p['gemstone']['title']} (from Rs {p['gemstone']['price_inr']:,.0f} on the JASTRO "
                       f"store), which supports " + ", ".join(p["gemstone"]["at_work"]) + ".")
            if sub:
                out.append(f"A lighter option is {sub['title']} (Rs {sub['price_inr']:,.0f}).")
        if a.get("next_strong_stretch"):
            w = a["next_strong_stretch"]
            out.append(f"Start wearing it before {_day(w['start'])}, so it backs your push in the stronger stretch "
                       f"until {_day(w['end'])}.")
    if p.get("bracelet") and asked in (None, p["bracelet"]["title"]):
        out.append(f"For daily wear, the {p['bracelet']['title']} (Rs {p['bracelet']['price_inr']:,.0f}) supports "
                   + ", ".join(p["bracelet"]["at_work"]) + ".")
    out.append("Have the stone checked once before you wear it; it supports your effort, it does not replace it.")
    return out


def brief(lines: list[str], n: int = 3) -> str:
    """Chat-sized fallback: the first lines that fit MAX_WORDS, then the question."""
    body, words = [], 0
    for line in lines[:-1]:
        if words + len(line.split()) > MAX_WORDS and body:
            break
        body.append(line)
        words += len(line.split())
    return "\n".join(body[:n] + [lines[-1]])


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
        return brief(_product_lines(f["product"]) + [""]).rstrip()
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
    return brief(lines + [""]).rstrip()

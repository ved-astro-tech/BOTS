# BOTS

Vedic astrology bots (career, health, marriage, relationship, wealth). The plan lives in the
[master plan doc](https://claude.ai/artifact/LpUfoXqNYq13sDvAr39QLM).

This first version is the **core engine plus the career baseline**, built for testing accuracy.
WhatsApp hosting comes later and will call the same functions.

## How a prediction is made

1. **Chart** (`astrobot/astro`): Swiss Ephemeris with the same settings as Jastro's `details_fetcher`
   (Lahiri, mean node, Placidus cusps, Krishnamurti ayanamsa for KP). D1, D9, D10, Vimshottari
   MD/AD/PD, transits, KP star and sub lords. Positions and dasha dates match `details_fetcher` exactly.
2. **Promise** (`astrobot/engine/rules.py`, `astrobot/knowledge/career.yaml`): rule cards from BPHS,
   Phaladeepika, Saravali and Jaimini, scored into a 0 to 100 career promise.
3. **Period**: every Pratyantardasha is scored by how strongly its MD, AD and PD lords signify the
   event's houses (rise: 10, 11, 6, 2, 1; setback: 12, 8, 5, 9; change: a mix).
4. **Trigger**: Jupiter and Saturn on the 10th from Lagna, the 10th from Moon, or the 10th lord
   (double transit).
5. **Evidence Pack** (`astrobot/engine/evidence.py`): promise, KP verdict on the 10th cusp sub lord,
   current dasha, top future and past windows with confidence, likely fields.
6. **Reading** (`astrobot/llm`): the LLM (OpenAI for now) gets the persona, the career prompt and the
   Evidence Pack, and may use only those facts.

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY for readings

# Evidence Pack (no API key needed)
python -m astrobot.cli evidence --date 1990-01-15 --time 10:30 --lat 28.6139 --lon 77.209

# Full reading
python -m astrobot.cli reading --date 1990-01-15 --time 10:30 --lat 28.6139 --lon 77.209 \
  --question "When will I get a promotion?"

# HTTP API
uvicorn astrobot.api:app --reload
# POST /v1/career/evidence  {"birth": {...}}
# POST /v1/career/reading   {"birth": {...}, "question": "..."}

pytest
```

## Measuring accuracy

```bash
python -m backtest.run backtest/cases/career.yaml --out backtest/reports/career.md
```

Each case is a birth plus dated career events (see `backtest/cases/career.example.yaml`). The runner
hides the events, scores every period, and reports where the real events land against chance:

| Measure | Chance level |
| --- | --- |
| Mean percentile of the event's period among periods within +/-5 years | 0.50 |
| Events in the top 20% of periods | 20% |
| Events inside one of the top-3 windows within +/-2 years | share of time the windows cover |

Real cases may contain client data, so `backtest/cases/*.yaml` is git-ignored except `*.example.yaml`.
Rule weights and house weights should only be tuned against this report, on cases not used for tuning.

## Layout

```
astrobot/astro      chart maths: ephemeris, vargas, dasha, transits, KP
astrobot/engine     rules, timing, evidence pack
astrobot/knowledge  one YAML per domain: config + rule cards
astrobot/llm        provider interface (OpenAI), prompts, reading
astrobot/api.py     FastAPI for testing
backtest/           accuracy harness
```

Adding a domain = a new `knowledge/<domain>.yaml` and `llm/prompts/<domain>.md`; new predicates only
when a card needs a new kind of condition.

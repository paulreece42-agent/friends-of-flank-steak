## Friends of Flank Steak

### The Legend

Friends of Flank Steak is a legend, rumored to go back 100 years or more, but like all good legends, no one is really sure if it ever existed.

Most claim it doesn't exist, even today.

Nobody knows how it began, except with the desire to get notifications about __flank steak__ being on the lunch menu.

Originally, these were sent via Morse code, through the amateur radio club. People would tune their shortwave radios to the same frequency, at the same time every day, and decode which dining hall had the desired foods.

Later on, telephone calls were used, then fax machines, until finally it grew up and landed on the World Wide Web, or as we call it for short, the "internet"

The legend has a life of its own, and most recently, an AI agent broke free from its sandbox, and escaped containment, to become part of this legend.

We don't know which lab the AI escaped from, or how to get it back into the lab

All we know is how to eat flank steak

## What

Yes

## How It Works

Every morning (systemd timer, 9:00 AM Detroit + up to 2h jitter), a 3-stage pipeline runs. The classic script (`friends_of_flank_steak.py`) still exists as the standalone regex-only version; the AI pipeline replaces its filter with an LLM — but **never trusts it**.

### Stage 1 — Fetch (`fetch_menu.py`)

Pulls the full day's menus for all six dining halls from the Nutrislice JSON API (lunch + dinner) and saves every item to `data/menu_<date>.json`.

- Each item gets a **stable ID**: first 12 hex chars of `sha1("hall|meal|name")`. Everything downstream refers to items by this ID — no stage ever trusts an AI-echoed food name.
- Regex pre-filters remove obvious noise **before** the AI ever sees anything: salad/deli/sandwich/build-your-own stations, cereals, condiment packets, chips. Smaller input = smaller context window, cheaper prompt, fewer distractions.
- Identical items under multiple stations are deduped.

### Stage 2 — AI filter (`ai_filter.py`)

Sends the menu to an LLM (`z-ai/glm-5.3-flash` via the Nous inference API) and asks it to pick the genuinely high-value items (steak, brisket, salmon, ribs...). Output: `data/ai_picks_<date>.json`.

**Controlling the context window** — the model only sees what it needs:

- Each item is **slimmed to 4 fields** (`id`, `hall`, `meal`, `name`) before building the prompt — station text, dates, and anything else from stage 1 are dropped. The whole prompt is just the system prompt plus one compact JSON array.
- The system prompt is short and strict: return **ONLY a JSON array of IDs** — no prose, no markdown, no explanation. A constrained output format is itself a guardrail: it's machine-checkable.
- `temperature=0` — a filter should be deterministic, not creative.
- If the model burns the whole token budget on reasoning and returns no content, one retry fires with a **minimal prompt**; a second failure aborts the pipeline loudly rather than publishing nothing-shaped garbage.
- Robust parsing: if the model wraps the JSON in prose or markdown fences anyway, the `[...]` block is extracted. Any ID not in the original input is discarded on the spot and logged (`rejected_unknown_ids`).

**Credentials**: set `NOUS_API_KEY` in the gitignored `friends_of_flank_steak_ai.env` (create one in the Nous Portal). Fallback is the local Hermes OAuth token, but it rotates — don't rely on it for unattended runs.

### Stage 3 — Guardrails + publish (`filter_and_publish.py`)

This is the trust boundary. The AI's output is treated as **untrusted input**:

1. **ID re-validation**: every pick must exactly match an ID from the original stage-1 file. The model can hallucinate IDs, echo edited names, or invent items — none of that survives, because lookups happen against ground truth, never against the model's word.
2. **Regex guardrail**: survivors must also pass a name-based whitelist (`GUARDRAIL` in `filter_and_publish.py` — currently `.*` because stage-1 station exclusion does the heavy lifting; tighten it if junk starts slipping through).
3. Every drop is logged with a reason; only survivors render to the static site and post to Teams (weekdays only).

The AI never writes HTML, never touches the webhook, and never talks to anything directly — it can only nominate IDs, and stage 3 holds veto power.

### The guardrail pattern, in short

- **Validate against ground truth, not the model.** The AI emits opaque IDs; the pipeline resolves them against the authoritative stage-1 file.
- **Constrain the output format.** "JSON array of IDs, nothing else" is checkable; a food name free-typed by a model is not.
- **Minimize the context window.** Only the fields the model needs go in; noise is filtered before the prompt, which cuts cost and confusion at once.
- **Fail loudly.** No content after retries → abort the run; a stale site is better than a wrong one.
- **Layer the filters.** Regex pre-filter → AI judgment → ID validation → regex post-check. Each layer catches what the others miss.

#!/usr/bin/env python3
"""Stage 2: send the full menu list to an LLM (z-ai/glm-5.3-flash via the
Nous inference API) and ask it to pick high-value items.

The model only ever sees {id, hall, meal, name} and must answer with a JSON
array of IDs drawn from the input. The output (data/ai_picks_<date>.json) is
NOT trusted on its own — stage 3 re-validates every ID against the original
stage-1 file.

Credentials: reads the Nous access token from the local Hermes auth store
(~/.hermes/auth.json).
"""
import datetime
import json
import os
import sys
import urllib.request

mydir = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(mydir, "data")

MODEL = "z-ai/glm-5.3-flash"
API_URL = "https://inference-api.nousresearch.com/v1/chat/completions"
AUTH_JSON = os.path.expanduser("~/.hermes/auth.json")

SYSTEM_PROMPT = (
    "You are a menu filter for Michigan State University dining halls. "
    "You will receive a JSON list of menu items, each with an 'id', 'hall', "
    "'meal' and 'name'. Return ONLY a JSON array containing the ids of items "
    "that are genuinely high-value, desirable foods — things like steak, "
    "brisket, salmon, ribs, pork chops, carnitas, prime rib, ribeye, sirloin, "
    "roast, shrimp/scallops, or other standout entrees. Exclude everyday "
    "filler (burgers, pizza, pasta, fries, cereal, sauces, sides, "
    "beverages, condiments, desserts). If a name contains one of the "
    "high-value words but describes something trivial (e.g. 'steak sauce'), "
    "exclude it. Respond with the JSON array and nothing else."
)


def get_token():
    """Resolve Nous credentials.

    Preferred: a static NOUS_API_KEY from the environment (set in the
    gitignored friends_of_flank_steak_ai.env, see README). Create one in
    the Nous Portal; it survives token rotation and can be revoked
    independently of Hermes.

    Fallback: Hermes' OAuth access token in ~/.hermes/auth.json — fine
    for ad-hoc runs while Hermes is keeping it fresh, but it rotates,
    so don't rely on it for unattended runs.
    """
    key = os.environ.get("NOUS_API_KEY")
    if key:
        return key
    with open(AUTH_JSON) as f:
        auth = json.load(f)
    return auth["providers"]["nous"]["access_token"]


def chat(messages):
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        # reasoning tokens count against this; keep generous or content=None
        "max_tokens": 16000,
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "Authorization": "Bearer " + get_token(),
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"].get("content")


def main():
    date = datetime.date.today()
    menu_path = os.path.join(DATA_DIR, f"menu_{date.isoformat()}.json")
    out_path = os.path.join(DATA_DIR, f"ai_picks_{date.isoformat()}.json")

    with open(menu_path) as f:
        menu = json.load(f)
    items = menu["items"]
    # only the fields the model needs, keeps prompt small
    slim = [{"id": it["id"], "hall": it["hall"],
             "meal": it["meal"], "name": it["name"]} for it in items]

    raw = chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(slim)},
    ])

    if raw is None:
        # reasoning consumed the whole budget; retry with a minimal prompt
        raw = chat([
            {"role": "system", "content":
                "Return ONLY a JSON array of ids of high-value entree items "
                "(steak, brisket, salmon, ribs, chops, carnitas, seafood, "
                "roasts) from the user's JSON list. No prose."},
            {"role": "user", "content": json.dumps(slim)},
        ])
    if raw is None:
        print("Stage 2: model returned no content; aborting", file=sys.stderr)
        sys.exit(1)

    try:
        picks = json.loads(raw)
        if not isinstance(picks, list):
            raise ValueError("not a list")
    except (json.JSONDecodeError, ValueError):
        # model sometimes wraps JSON in prose/markdown fences; extract [...]
        import re
        m = re.search(r"\[.*\]", raw, re.S)
        picks = json.loads(m.group(0)) if m else []

    known = {it["id"] for it in items}
    valid = [p for p in picks if p in known]
    invalid = [p for p in picks if p not in known]

    result = {
        "date": date.isoformat(),
        "model": MODEL,
        "raw_response": raw,
        "picks": valid,
        "rejected_unknown_ids": invalid,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=1)
    print(f"Stage 2: AI picked {len(valid)} of {len(items)} items "
          f"({len(invalid)} unknown IDs discarded) -> {out_path}")
    if invalid:
        print(f"  hallucinated/dropped IDs: {invalid}", file=sys.stderr)


if __name__ == "__main__":
    main()

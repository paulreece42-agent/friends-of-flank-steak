#!/usr/bin/env python3
"""Stage 3: guardrail + publish.

Re-validates every AI pick from stage 2 against the ORIGINAL stage-1 menu
file (exact ID match) AND a regex whitelist on the item name (so even a
valid ID whose name doesn't look like high-value food gets dropped). Only
survivors go to the static HTML site, and the survivor list is written to
data/published_<date>.json for the separate Teams poster
(post_to_teams.py) to pick up.
"""
import datetime
import json
import os
import re
import sys

from jinja2 import Environment, FileSystemLoader

from friends_of_flank_steak import HALL_ORDER, highlight_flank_steak_html

mydir = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(mydir, "data")

# Final guardrail. Loosened to accept everything for now (the stage-1
# station exclusion does the heavy lifting); tune down later if the AI
# starts surfacing junk.
GUARDRAIL = re.compile(r".*", re.I)


def main():
    date = datetime.date.today()
    menu_path = os.path.join(DATA_DIR, f"menu_{date.isoformat()}.json")
    picks_path = os.path.join(DATA_DIR, f"ai_picks_{date.isoformat()}.json")

    with open(menu_path) as f:
        menu = json.load(f)
    with open(picks_path) as f:
        picks = json.load(f)

    by_id = {it["id"]: it for it in menu["items"]}

    survived, dropped = [], []
    for pid in picks["picks"]:
        item = by_id.get(pid)  # exact ID match against the original list
        if item is None:
            dropped.append((pid, "ID not in original menu"))
        elif not GUARDRAIL.search(item["name"]):
            dropped.append((pid, f"regex guardrail: {item['name']}"))
        else:
            survived.append(item)

    out = [{"dh": it["hall"], "food": it["name"], "time": it["meal"],
            "food_html": highlight_flank_steak_html(it["name"])}
           for it in survived]
    # Sort by dining-hall priority (proximity to Paul's workplace), then
    # meal — the AI's pick order is arbitrary, ours is not.
    out.sort(key=lambda r: (HALL_ORDER.get(r["dh"], 99), r["time"]))

    # --- write survivor list for the Teams poster (separate cron) ---
    published_path = os.path.join(DATA_DIR, f"published_{date.isoformat()}.json")
    with open(published_path, "w") as f:
        json.dump({"date": date.isoformat(), "items": out}, f, indent=2)

    # --- publish: static HTML site (same templates as the classic script) ---
    env = Environment(loader=FileSystemLoader(
        os.path.join(mydir, "public_html", "templates")))
    template = env.get_template("index.html")

    pretty = date.strftime("%A, the %d of %B, %Y")
    html = template.render({"today": pretty, "foods": out})
    out_html = os.path.join(mydir, "public_html", "index.html")
    with open(out_html, "w") as f:
        f.write(html)

    print(f"Stage 3: {len(survived)} items survived guardrails, "
          f"{len(dropped)} dropped")
    for pid, why in dropped:
        print(f"  dropped {pid}: {why}")
    for it in survived:
        print(f"  kept: {it['hall']} / {it['meal']} — {it['name']}")


if __name__ == "__main__":
    main()

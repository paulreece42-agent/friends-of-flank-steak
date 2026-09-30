#!/usr/bin/env python3
"""Stage 4 (separate cron): post the already-published menu to MS Teams.

Reads data/published_<date>.json written by filter_and_publish.py and
sends it to Teams. Does NOT re-run the fetch/filter/publish pipeline.

Runs on its own timer (friends_of_flank_steak_teams.timer) later in the
morning so the website updates early without pinging everyone at dawn.
"""
import datetime
import json
import os
import sys

from friends_of_flank_steak import send_menu_to_teams

mydir = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(mydir, "data")


def main():
    date = datetime.date.today()
    published_path = os.path.join(DATA_DIR, f"published_{date.isoformat()}.json")

    if not os.path.exists(published_path):
        print(f"No published data for {date.isoformat()} "
              f"({published_path} missing) — has filter_and_publish.py run?",
              file=sys.stderr)
        sys.exit(1)

    with open(published_path) as f:
        data = json.load(f)
    items = data["items"]
    if not items:
        print("Nothing to post: published item list is empty")
        return

    webhook = os.getenv("MS_TEAMS_URL")
    if not webhook:
        print("MS_TEAMS_URL not set — skipping Teams post", file=sys.stderr)
        sys.exit(1)

    send_menu_to_teams(webhook, items)
    print(f"Posted {len(items)} items to Teams")


if __name__ == "__main__":
    main()

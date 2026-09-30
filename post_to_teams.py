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


def load_webhook():
    """MS_TEAMS_URL from the environment, else parsed from the env file
    (same KEY=VALUE format systemd's EnvironmentFile uses)."""
    webhook = os.getenv("MS_TEAMS_URL")
    if webhook:
        return webhook
    env_file = os.path.join(mydir, "friends_of_flank_steak_ai.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("MS_TEAMS_URL="):
                    return line.split("=", 1)[1].strip()
    return None


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

    # Belt and suspenders: the filename says "today" but make sure the
    # data inside actually is today's, so a stale/clock-skew run can
    # never post yesterday's (or any old) menu.
    if data.get("date") != date.isoformat():
        print(f"Refusing to post: published data is for {data.get('date')}, "
              f"not today ({date.isoformat()})", file=sys.stderr)
        sys.exit(1)

    items = data["items"]
    if not items:
        print("Nothing to post: published item list is empty")
        return

    webhook = load_webhook()
    if not webhook:
        print("MS_TEAMS_URL not set — skipping Teams post", file=sys.stderr)
        sys.exit(1)

    send_menu_to_teams(webhook, items)
    print(f"Posted {len(items)} items to Teams")


if __name__ == "__main__":
    main()

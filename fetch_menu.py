#!/usr/bin/env python3
"""Stage 1: fetch the FULL MSU dining hall menus (no filtering) and save
them to data/menu_<date>.json.

Each item gets a stable ID (sha1 of hall|meal|name) so later stages can
refer to items without ever trusting an AI-echoed name.
"""
import datetime
import hashlib
import json
import os
import re
import sys

import requests

from friends_of_flank_steak import HEADERS, diningHalls, API, HALL_ORDER

mydir = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(mydir, "data")


def item_id(hall, meal, name):
    return hashlib.sha1(f"{hall}|{meal}|{name}".encode()).hexdigest()[:12]


# Sections that flood results with trivially-matching items ("shrimp salad",
# "roast beef sandwich"). Matched case-insensitively against the station
# header text that precedes each item in the Nutrislice day payload.
EXCLUDED_STATIONS = re.compile(
    r"deli|salad|sandwich|stacks|build.?your.?own|topping|toppings|bar|"
    r"beverage|bread|dessert|ice cream|miscellaneous|side|condiment",
    re.I,
)

# Junk that hides under "Entrees": breakfast cereal, condiment packets,
# chips/dips. Cereals especially are pure noise.
EXCLUDED_ITEMS = re.compile(
    r"apple jacks|captain crunch|cinnamon toast crunch|cocoa (puffs|pebbles)|"
    r"golden grahams|fruit loops|froot loops|lucky charms|cheerios|"
    r"frosted flakes|rice krispies|special k|corn pops|honey bunches|"
    r"chex|shredded wheat|life cereal|kellogg|general mills|"
    r"(equal|splenda|sugar|sweet.{0,3}and.{0,3}low) packet|chips and salsa",
    re.I,
)


def main():
    date = datetime.date.today()
    out_path = os.path.join(DATA_DIR, f"menu_{date.isoformat()}.json")

    session = requests.Session()
    session.headers.update(HEADERS)

    items = []
    for dh in diningHalls:
        for meal in ("lunch", "dinner"):
            url = API.format(slug=dh["slug"], meal=meal,
                             y=date.year, m=date.month, d=date.day)
            try:
                r = session.get(url, timeout=30)
                r.raise_for_status()
                week = r.json()
            except (requests.RequestException, json.JSONDecodeError) as e:
                print(f"  ! {dh['slug']}/{meal}: {e}", file=sys.stderr)
                continue
            day = next((d for d in week.get("days", [])
                        if d.get("date") == date.isoformat()), None)
            if not day:
                continue
            station = ""
            for mi in day.get("menu_items", []):
                if mi.get("is_station_header"):
                    station = (mi.get("text") or "").strip()
                    continue
                if EXCLUDED_STATIONS.search(station):
                    continue  # deli / salad / sandwich bars
                food = mi.get("food")
                if not food:
                    continue  # station headers / section titles
                name = (food.get("name") or "").strip()
                if not name:
                    continue
                if EXCLUDED_ITEMS.search(name):
                    continue  # cereal / condiment noise
                items.append({
                    "id": item_id(dh["name"], meal, name),
                    "hall": dh["name"],
                    "meal": meal.capitalize(),
                    "station": station,
                    "name": name,
                })

    # dedupe identical (hall, meal, name) appearing under multiple stations
    seen = set()
    unique = []
    for it in items:
        key = (it["hall"], it["meal"], it["name"])
        if key not in seen:
            seen.add(key)
            unique.append(it)

    # Sort by dining-hall priority (HALL_ORDER), then by meal, so the
    # AI sees a stable, sensibly ordered list regardless of fetch order.
    unique.sort(key=lambda it: (HALL_ORDER.get(it["hall"], 99), it["meal"]))

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"date": date.isoformat(), "items": unique}, f, indent=1)
    print(f"Stage 1: saved {len(unique)} menu items to {out_path}")


if __name__ == "__main__":
    main()

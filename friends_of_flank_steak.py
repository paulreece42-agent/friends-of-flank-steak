#!/bin/env python3
#
# Pull MSU dining hall menus from Nutrislice's JSON API (replaces the old
# eatatstate.msu.edu HTML scraping, which broke when MSU moved to Nutrislice),
# filter for high-value items, update the static HTML site, and optionally
# post to MS Teams.
#
# Run as a cron or somethin:
#
# Systemd timer even better, on RHEL systems:
#
# cp -arv friends_of_flank_steak.timer /usr/lib/systemd/system/
# cp -arv friends_of_flank_steak.service /usr/lib/systemd/system/
# systemctl daemon-reload
# systemctl enable --now friends_of_flank_steak.timer
# systemctl status friends_of_flank_steak.timer
#
# Env:
#   MS_TEAMS_URL   MS Teams Workflow webhook URL (optional; posts only if set)
#
##
import datetime
import json
import os
import re
import sys
import requests
from jinja2 import Environment, FileSystemLoader
today_idx = datetime.datetime.today().weekday()
# Case-insensitive filter for high-value items. Override via argv[1].
winningFoodsFilter = re.compile(r"steak|brisket|salmon|ribs|Carnitas|chops|sirloin|ribeye", re.I)
mydir = os.path.dirname(os.path.abspath(__file__))
outputFileName = os.path.join(mydir, 'public_html', 'index.html')
WEBHOOK_URL = os.getenv('MS_TEAMS_URL')
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}
# Nutrislice location slugs (replaces the old htmlName URL-escaped names)
diningHalls = [
    {"name": "Shaw",   "slug": "the-vista-at-shaw"},
    {"name": "SnyPhi", "slug": "the-gallery-at-synderphillips"},
    {"name": "Akers",  "slug": "the-edge-at-akers"},
    {"name": "Case",   "slug": "south-pointe-at-case"},
    {"name": "Brody",  "slug": "brody-square"},
    {"name": "Landon", "slug": "heritage-commons-at-landon"},
]
API = "https://msu.api.nutrislice.com/menu/api/weeks/school/{slug}/menu-type/{meal}/{y}/{m:02d}/{d:02d}/"

# Preferred display order of dining halls (proximity to Paul's workplace):
# Shaw, SnyPhi, Akers, Case, Brody, Landon.
HALL_ORDER = {dh["name"]: i for i, dh in enumerate(diningHalls)}


def getDiningHall(session, slug, date):
    """Fetch lunch+dinner for a hall via the Nutrislice JSON API.
    Returns a list of {"food": name, "time": "Lunch"|"Dinner"} for items
    matching winningFoodsFilter. (Old scraper returned a "time" key too,
    so downstream code is unchanged.)
    """
    winfoods = []
    for meal in ("lunch", "dinner"):
        url = API.format(slug=slug, meal=meal, y=date.year, m=date.month, d=date.day)
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            week = r.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"  ! {slug}/{meal}: {e}", file=sys.stderr)
            continue
        day = next((d for d in week.get("days", [])
                    if d.get("date") == date.isoformat()), None)
        if not day:
            continue
        for item in day.get("menu_items", []):
            food = item.get("food")
            if not food:
                continue  # station headers / section titles
            name = food.get("name", "")
            if winningFoodsFilter.search(name):
                winfoods.append({"food": name, "time": meal.capitalize()})
    return winfoods
def send_menu_to_teams(webhook_url, menu_items):
    """
    Sends a dining menu to Teams as a compact, chat-friendly card:
    one bold heading per dining hall, then a bullet line per item
    ("Meal — Food"). menu_items must already be sorted by hall/meal.
    :param webhook_url: The MS Teams Workflow Webhook URL
    :param menu_items: List of dicts, e.g. [{"food": "Item", "time": "Lunch", "dh": "Akers"}]
    """
    # group items in order of first appearance (list is pre-sorted)
    groups = []  # [(hall, [items...])]
    for item in menu_items:
        if not groups or groups[-1][0] != item.get("dh", ""):
            groups.append((item.get("dh", ""), []))
        groups[-1][1].append(item)

    card_body: list = [
        {
            "type": "TextBlock",
            "text": "Good Foods on Campus Today",
            "size": "Large",
            "weight": "Bolder",
            "color": "Accent"
        }
    ]
    for hall, items in groups:
        card_body.append({
            "type": "TextBlock",
            "text": hall,
            "weight": "Bolder",
            "size": "Medium",
            "separator": True
        })
        card_body.append({
            "type": "TextBlock",
            "text": "\n".join(f"• {it.get('time', '')} — {it.get('food', '')}"
                              for it in items),
            "wrap": True
        })
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "body": card_body,
                    "$schema": "http://adaptivecards.io",
                    "version": "1.4"
                }
            }
        ]
    }
    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        print("Menu successfully posted to Teams!")
    except requests.exceptions.RequestException as e:
        # Power Automate puts the real reason in the response body — show it.
        body = ""
        if e.response is not None:
            body = e.response.text[:2000]
        print(f"Error posting to Teams: {e}\nResponse body: {body}")
        # Fallback: some Power Automate "Post to channel" flow templates expect
        # the adaptive card content as a JSON *string*, not an object.
        if e.response is not None and e.response.status_code == 400:
            try:
                fb = json.loads(json.dumps(payload))
                fb["attachments"][0]["content"] = json.dumps(
                    fb["attachments"][0]["content"])
                r2 = requests.post(webhook_url, json=fb)
                r2.raise_for_status()
                print("Menu successfully posted to Teams (stringified card fallback)!")
            except requests.exceptions.RequestException as e2:
                body2 = ""
                if e2.response is not None:
                    body2 = e2.response.text[:2000]
                print(f"Stringified fallback also failed: {e2}\nResponse body: {body2}")
def main():
    env = Environment(loader=FileSystemLoader(os.path.join(mydir, 'public_html', 'templates')))
    template = env.get_template('index.html')
    markdown_template = env.get_template('markdown.html')
    today = datetime.date.today()
    prettyToday = today.strftime("%A, the %d of %B, %Y")
    session = requests.Session()
    session.headers.update(HEADERS)
    output = []
    for dh in diningHalls:
        foods = getDiningHall(session, dh['slug'], today)
        for f in foods:
            output.append({"dh": dh['name'], "food": f['food'], "time": f['time']})
    html_output = template.render({"today": prettyToday, "foods": output})
    os.makedirs(os.path.dirname(outputFileName), exist_ok=True)
    with open(outputFileName, 'w') as f:
        f.write(html_output)
    print(f"Wrote {outputFileName} ({len(output)} matching items)")
    markdown_output = markdown_template.render({"today": prettyToday, "foods": output})
    # on weekdays, post to teams
    if WEBHOOK_URL and today_idx <= 4:
        send_menu_to_teams(WEBHOOK_URL, output)
if __name__ == "__main__":
    main()

#!/bin/env python3
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
##
import requests
import re
import datetime
from jinja2 import Environment, FileSystemLoader
import os
import json

today_idx = datetime.datetime.today().weekday()

allFoodsFilter = re.compile(".*div class=\"meal-title (?P<time>\w+)\">(?P<food>.+)<", re.I)
winningFoodsFilter = re.compile(".*(steak|brisket|salmon).*", re.I)
outputFileName = 'public_html/index.html'
WEBHOOK_URL = os.getenv('MS_TEAMS_URL')


diningHalls = [
    {"name": "Brody", "htmlName": "Brody%20Square"},
    {"name" : "Akers", "htmlName": "The%20Edge%20at%20Akers"},
    {"name": "Case", "htmlName": "South%20Pointe%20at%20Case"},
    {"name": "Landon", "htmlName": "Heritage%20Commons%20at%20Landon"},
    {"name": "Shaw", "htmlName": "The%20Vista%20at%20Shaw"},
    {"name": "SnyPhi", "htmlName": "The%20Gallery%20at%20Snyder%20Phillips"}
]

def getDiningHall(dh, whatday):
    response = requests.get(f"https://eatatstate.msu.edu/menu/{dh}/all/{whatday}")
    response.text
    allfoods = []
    winfoods = []
    for line in response.text.split('\n'):
        m = allFoodsFilter.search(line)
        if m:
            allfoods.append(m.groupdict())
            if winningFoodsFilter.match(line):
                    winfoods.append(m.groupdict())

    return(winfoods)

def send_menu_to_teams(webhook_url, menu_items):
    """
    Sends a dining menu to Teams using a ColumnSet-based table.
    
    :param webhook_url: The MS Teams Workflow Webhook URL
    :param menu_items: List of dicts, e.g., [{"Food": "Item", "Time": "Lunch", "Hall": "Akers"}]
    """
    
    # Helper to generate a standardized row
    def create_row(col1, col2, col3, is_header=False):
        weight = "Bolder" if is_header else "Default"
        # Optional: Add a light gray background to the header row
        style = "emphasis" if is_header else "default"
        
        return {
            "type": "ColumnSet",
            "style": style,
            "columns": [
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [{"type": "TextBlock", "text": col1, "weight": weight, "wrap": True}]
                },
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [{"type": "TextBlock", "text": col2, "weight": weight, "wrap": True}]
                },
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [{"type": "TextBlock", "text": col3, "weight": weight, "wrap": True}]
                }
            ],
            "separator": not is_header  # Adds a line between data rows
        }

    # Build the Card Body starting with Title and Header
    card_body = [
        {
            "type": "TextBlock", 
            "text": "Good Foods on Campus Today", 
            "size": "Large", 
            "weight": "Bolder",
            "color": "Accent"
        },
        create_row("Food", "Time", "Dining Hall", is_header=True)
    ]

    # Dynamically add rows from the passed argument
    for item in menu_items:
        card_body.append(
            create_row(item.get("food", ""), item.get("time", ""), item.get("dh", ""))
        )

    # Construct the full Adaptive Card payload
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
        print(f"Error posting to Teams: {e}")


def send_teams_workflow_message(webhook_url, title, message):
    # The payload structure for modern "Workflows" typically uses Adaptive Cards
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Medium",
                            "weight": "Bolder",
                            "text": title
                        },
                        {
                            "type": "TextBlock",
                            "text": message,
                            "wrap": True
                        }
                    ],
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.4"
                }
            }
        ]
    }

    try:
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        print("Successfully sent message to Teams!")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send message: {e}")


def main():
    # make paths relative to where the script is
    mydir = os.path.dirname(__file__)
    env = Environment(loader=FileSystemLoader(os.path.join(mydir, 'public_html/templates')))
    template = env.get_template('index.html')
    markdown_template = env.get_template('markdown.html')
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    prettyToday = datetime.datetime.now().strftime("%A, the %d of %B, %Y")
    output = []
    for dh in diningHalls:
        foods = getDiningHall(dh['htmlName'], today)
        if len(foods) > 0:
            for f in foods:
                output.append({"dh": dh['name'], "food": f['food'], "time": f['time']})
    
    html_output = template.render({"today": prettyToday, "foods": output})
    with open(os.path.join(mydir, outputFileName), 'w') as f:
        f.write(html_output)
    markdown_output = markdown_template.render({"today": prettyToday, "foods": output})
    
    # on weekdays, post to teams
    if today_idx <= 4:
        send_menu_to_teams(WEBHOOK_URL, output)

if __name__ == "__main__":
    main()

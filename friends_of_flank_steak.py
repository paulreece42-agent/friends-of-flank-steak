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

allFoodsFilter = re.compile(".*div class=\"meal-title (?P<time>\w+)\">(?P<food>.+)<", re.I)
winningFoodsFilter = re.compile(".*(steak|brisket|salmon).*", re.I)
outputFileName = 'public_html/index.html'

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

def main():
    # make paths relative to where the script is
    mydir = os.path.dirname(__file__)
    env = Environment(loader=FileSystemLoader(os.path.join(mydir, 'public_html/templates')))
    template = env.get_template('index.html')
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

if __name__ == "__main__":
    main()

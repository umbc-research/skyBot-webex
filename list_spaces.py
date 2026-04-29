"""
Utility script to list all spaces and teams the bot is a member of.
Run this after creating a space and adding the bot to it.
"""

import os
import dotenv
from webexteamssdk import WebexTeamsAPI

dotenv.load_dotenv()

token = os.getenv("WEBEX_BOT_TOKEN")
if not token:
    print("Error: WEBEX_BOT_TOKEN not set in .env")
    exit(1)

api = WebexTeamsAPI(access_token=token)

# Get bot info
me = api.people.me()
print(f"Bot: {me.displayName}")
print(f"Bot ID: {me.id}")
print(f"Bot Email: {me.emails[0] if me.emails else 'N/A'}")
print()

# List teams
print("Teams the bot is in:")
print("-" * 60)
teams = list(api.teams.list())
if not teams:
    print("No teams found. Add the bot to a team first.")
else:
    for team in teams:
        print(f"Title: {team.name}")
        print(f"ID:    {team.id}")
        print("-" * 60)
print()

# List spaces
print("Spaces the bot is in:")
print("-" * 60)
spaces = list(api.rooms.list())
if not spaces:
    print("No spaces found. Add the bot to a space first.")
else:
    for space in spaces:
        print(f"Title: {space.title}")
        print(f"ID:    {space.id}")
        print(f"Type:  {space.type}")
        print("-" * 60)

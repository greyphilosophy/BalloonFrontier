#!/usr/bin/env python3
"""Balloon Frontier - Discord Bot Launcher"""
import os
import sys

# Load token from .env
with open(os.path.join(os.path.dirname(__file__), '.env')) as f:
    for line in f:
        if line.startswith('DISCORD_BF_TOKEN=***            token = line.split('=', 1)[1].strip()
            os.environ['DISCORD_BF_TOKEN'] = token
            print(f"Loaded token: {token[:10]}...{token[-10:]} (len={len(token)}", flush=True)
            break
        else:
            print('Token not found in .env', flush=True)
            sys.exit(1)

# Import and run bot
from discord_bot import bot
bot.run(token)
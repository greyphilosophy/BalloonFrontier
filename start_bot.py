#!/usr/bin/env python3
"""Balloon Frontier - Discord Bot Launcher"""
import os
import sys

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
token = None

with open(env_path) as f:
    for line in f:
        if line.startswith('DISCORD_BF_TOKEN='):
            token = line.split('=', 1)[1].strip()
            break

if token:
    os.environ['DISCORD_BF_TOKEN'] = token
    print(f'Bot token loaded from .env (len={len(token)})')
else:
    print('Token not found in .env', flush=True)
    sys.exit(1)

# Import and run bot
from discord_bot import bot
bot.run(token)

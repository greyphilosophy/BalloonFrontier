#!/usr/bin/env python3
"""Balloon Frontier - Discord Bot Launcher

Launch paths:
  DISCORD_BF_TOKEN="abc" python3 start_bot.py        # env var (checked first)
  echo 'DISCORD_BF_TOKEN=abc' >> .env && python3 start_bot.py   # .env fallback
"""
import os
import sys

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

# 1. Check environment variable first
token = os.environ.get("DISCORD_BF_TOKEN")

# 2. Fall back to .env file
if not token and os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith("DISCORD_BF_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break

if not token:
    print("DISCORD_BF_TOKEN is not configured")
    sys.exit(1)

from discord_bot import bot
bot.run(token)

#!/bin/bash
# Runner script for cron - activates venv and runs the bot
cd "$(dirname "$0")"
source venv/bin/activate
python3 main.py >> bot.log 2>&1

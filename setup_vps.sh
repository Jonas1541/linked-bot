#!/bin/bash
# ===========================================
#  LinkedIn Bot - VPS Setup Script
#  Tested on Ubuntu 22.04 / Debian 12
# ===========================================
set -e

echo "=== LinkedIn Bot VPS Setup ==="

# 1. System dependencies
echo "[1/5] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    wget curl unzip \
    fonts-liberation libnss3 libatk-bridge2.0-0 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libasound2t64 libpango-1.0-0 libcairo2 \
    libatspi2.0-0 libgtk-3-0 xdg-utils cron xvfb

# Pre-accept Microsoft fonts EULA to prevent interactive prompt hanging and install fonts
echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | sudo debconf-set-selections
sudo apt-get install -y ttf-mscorefonts-installer

# 2. Python virtual environment
echo "[2/5] Setting up Python virtual environment..."
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate

# 3. Python dependencies
echo "[3/5] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Playwright browser
echo "[4/5] Installing Chromium for Playwright..."
playwright install chromium
playwright install-deps chromium

# 5. Environment file
echo "[5/5] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Created .env from template. EDIT IT with your credentials!"
    echo "  → nano .env"
else
    echo "✓ .env already exists. Skipping."
fi

# 6. Setup cron
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your credentials:  nano .env"
echo "  2. Test the bot:                     source venv/bin/activate && python3 main.py"
echo "  3. Set up cron:"
echo ""
echo "     crontab -e"
echo "     # Add this line (runs 3x/day at peak hours):"
echo "     0 8,12,17 * * * ${SCRIPT_DIR}/run.sh"
echo ""

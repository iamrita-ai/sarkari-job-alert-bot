#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# One-shot setup for running the bot inside Termux on an Android phone.
# Usage:
#   pkg install git -y && git clone https://github.com/iamrita-ai/sarkari-job-alert-bot
#   cd sarkari-job-alert-bot && bash scripts/termux_setup.sh
# =============================================================================
set -euo pipefail

echo "==> [1/5] Updating Termux packages"
pkg update -y && pkg upgrade -y
pkg install python git -y

echo "==> [2/5] Creating virtual environment"
python -m venv "$HOME/sarkari-bot-venv"
# shellcheck disable=SC1091
source "$HOME/sarkari-bot-venv/bin/activate"
pip install --upgrade pip
pip install --retries 5 --timeout 120 -r requirements.txt

echo "==> [3/5] Preparing .env"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "A template .env was created."
fi

# Phone deployments don't need the HTTP health port
grep -q "^ENABLE_HEALTH_SERVER=false" .env || \
  printf '\n# Termux/phone: no cloud health check needed\nENABLE_HEALTH_SERVER=false\n' >> .env

echo "==> [4/5] Background helper scripts"
cat > start_bot.sh <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
cd "$(dirname "$0")"
source "$HOME/sarkari-bot-venv/bin/activate"
termux-wake-lock
exec python -m bot.main
EOF
chmod +x start_bot.sh

cat > stop_bot.sh <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
pkill -f "python -m bot.main" && termux-wake-unlock || echo "Bot is not running"
EOF
chmod +x stop_bot.sh

echo "==> [5/5] Done"
cat <<GUIDE

Next steps:
  1. nano .env            # paste your BOT_TOKEN, then Ctrl+O, Enter, Ctrl+X
  2. ./start_bot.sh       # run in foreground (Ctrl+C stops it)

Run 24/7 in the background:
  nohup ./start_bot.sh > bot.log 2>&1 &
  tail -f bot.log                          # watch logs
  ./stop_bot.sh                            # stop it

Auto-start after phone reboot:
  pkg install termux-services termux-boot -y   # then see DEPLOYMENT.md
GUIDE

#!/usr/bin/env bash
# Sum Bot installer / updater (Ubuntu/Debian, run as root)
#
# Install or update:
#   bash <(curl -fsSL https://raw.githubusercontent.com/iLiYAMlPF/PasarGuard-Calculator/main/install.sh)
#
# Re-running this script updates the code and keeps your .env and data.db.
# After installation you can also use:  sum-bot update
set -euo pipefail

# Never run from inside the install directory (it may be moved/replaced)
cd /

REPO_URL="${REPO_URL:-https://github.com/iLiYAMlPF/PasarGuard-Calculator.git}"
BRANCH="${BRANCH:-main}"
DIR="${DIR:-/opt/sum-bot}"
SERVICE="sum-bot"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root (e.g. sudo bash install.sh)"; exit 1
fi

echo "==> Installing system packages"
apt-get update -y >/dev/null
apt-get install -y git python3 python3-venv python3-pip >/dev/null

BAK=""
if [ -d "$DIR" ] && [ ! -d "$DIR/.git" ]; then
  BAK="$DIR.bak.$(date +%s)"
  mv "$DIR" "$BAK"
  echo "==> Old folder moved to $BAK"
fi

if [ -d "$DIR/.git" ]; then
  echo "==> Updating code"
  git -C "$DIR" fetch --quiet origin "$BRANCH"
  git -C "$DIR" reset --hard --quiet "origin/$BRANCH"
else
  echo "==> Downloading code"
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$DIR"
fi

# Restore settings and database from the old folder (if any)
if [ -n "$BAK" ]; then
  for f in .env data.db; do
    if [ -f "$BAK/$f" ]; then cp "$BAK/$f" "$DIR/$f"; fi
  done
fi

echo "==> Creating Python virtualenv and installing dependencies"
[ -x "$DIR/venv/bin/python" ] || python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --upgrade pip
"$DIR/venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

if [ ! -f "$DIR/.env" ]; then
  echo
  echo "=============================================="
  echo " Configuration (asked only once)"
  echo "=============================================="
  echo " You will be asked for 4 values:"
  echo "  1) Bot token      - create a NEW bot in @BotFather (/newbot) and paste its token"
  echo "  2) Group chat ID  - numeric ID of your group, starts with -100 (e.g. -1001234567890)"
  echo "  3) Topic ID       - the topic to watch; 1 = General topic"
  echo "  4) Your user ID   - your numeric Telegram ID; only you can use the bot"
  echo "                      (send /myid to the bot to get it, or press Enter to skip for now)"
  echo "=============================================="
  echo

  TOKEN=""
  while [ -z "$TOKEN" ]; do
    read -r -s -p "[1/4] Enter the bot token (input is hidden): " TOKEN < /dev/tty; echo
  done
  read -r -p "[2/4] Enter the group chat ID, e.g. -1001234567890 (Enter = any group): " CHAT < /dev/tty || true
  read -r -p "[3/4] Enter the topic ID (Enter = 1, the General topic): " TOPIC < /dev/tty || true
  read -r -p "[4/4] Enter YOUR numeric Telegram user ID (Enter = skip for now): " OWNER < /dev/tty || true

  umask 077
  printf 'BOT_TOKEN=%s\nCHAT_ID=%s\nTOPIC_ID=%s\nOWNER_IDS=%s\n' \
    "$TOKEN" "${CHAT:-}" "${TOPIC:-1}" "${OWNER:-}" > "$DIR/.env"
  echo "==> Settings saved to $DIR/.env"
fi
chmod 600 "$DIR/.env"

# --- CLI begin
echo "==> Installing the 'sum-bot' command"
{
  echo '#!/usr/bin/env bash'
  echo "DIR=\"$DIR\""
  echo "SERVICE=\"$SERVICE\""
  echo "BRANCH=\"$BRANCH\""
  cat <<'CLI'
ver() { cat "$DIR/VERSION" 2>/dev/null || echo unknown; }
case "${1:-help}" in
  update)
    [ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo sum-bot update)"; exit 1; }
    old="$(ver)"
    git -C "$DIR" fetch --quiet origin "$BRANCH"
    git -C "$DIR" reset --hard --quiet "origin/$BRANCH"
    "$DIR/venv/bin/pip" install --quiet -r "$DIR/requirements.txt"
    systemctl restart "$SERVICE"
    echo "✅ Updated: $old -> $(ver)"
    ;;
  version) echo "Sum Bot version: $(ver)" ;;
  status)  systemctl status "$SERVICE" --no-pager ;;
  logs)    journalctl -u "$SERVICE" -f ;;
  restart) systemctl restart "$SERVICE" && echo "Restarted." ;;
  config)  "${EDITOR:-nano}" "$DIR/.env" && systemctl restart "$SERVICE" && echo "Restarted." ;;
  uninstall)
    [ "$(id -u)" -eq 0 ] || { echo "Run as root"; exit 1; }
    read -r -p "This removes the bot and its settings. Type YES to continue: " a
    [ "$a" = "YES" ] || { echo "Cancelled."; exit 0; }
    if [ -f "$DIR/data.db" ]; then
      cp "$DIR/data.db" /root/sum-bot-data.db.bak && echo "Database backup: /root/sum-bot-data.db.bak"
    fi
    systemctl stop "$SERVICE" 2>/dev/null || true
    systemctl disable "$SERVICE" 2>/dev/null || true
    rm -f "/etc/systemd/system/$SERVICE.service"
    systemctl daemon-reload
    rm -rf "$DIR"
    rm -f /usr/local/bin/sum-bot
    echo "Removed."
    ;;
  *)
    echo "Sum Bot $(ver)"
    echo "Usage: sum-bot <command>"
    echo "  update     download the latest version from GitHub and restart"
    echo "  version    show the installed version"
    echo "  status     show service status"
    echo "  logs       follow live logs"
    echo "  restart    restart the bot"
    echo "  config     edit .env and restart"
    echo "  uninstall  remove the bot (keeps a database backup)"
    ;;
esac
CLI
} > /usr/local/bin/sum-bot
chmod +x /usr/local/bin/sum-bot
# --- CLI end

echo "==> Creating systemd service"
cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=Sum Bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
EnvironmentFile=$DIR/.env
ExecStart=$DIR/venv/bin/python sum_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1
systemctl restart "$SERVICE"
sleep 3

if systemctl is-active --quiet "$SERVICE"; then
  echo
  echo "✅ Bot is running."
  echo
  echo "Next steps in Telegram:"
  echo "  - Add the bot to your group and make it an ADMIN"
  echo "  - @BotFather -> /setprivacy -> choose the bot -> Disable (then re-add the bot to the group)"
  echo "  - @BotFather -> enable Bot-to-Bot Communication Mode for BOTH bots (PasarGuard's and this one)"
  echo "  - Send /myid in the group, put the number in OWNER_IDS if you skipped it:"
  echo "      nano $DIR/.env && systemctl restart $SERVICE"
  echo
  echo "Installed version: $(cat "$DIR/VERSION" 2>/dev/null || echo unknown)"
  echo
  echo "Useful commands (run 'sum-bot' to see all):"
  echo "  sum-bot update      # update to the latest version from GitHub"
  echo "  sum-bot logs        # live logs"
  echo "  sum-bot config      # edit settings and restart"
  echo "You can also send /update to the bot in Telegram (owner only)."
else
  echo "❌ The service failed to start. Last logs:"
  journalctl -u "$SERVICE" -n 20 --no-pager
  exit 1
fi

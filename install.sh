#!/usr/bin/env bash
# نصب و آپدیت ربات روی سرور (Ubuntu/Debian)
#   نصب:    bash <(curl -fsSL https://raw.githubusercontent.com/USERNAME/sum-bot/main/install.sh)
#   آپدیت: همین دستور را دوباره اجرا کنید (تنظیمات و دیتابیس حفظ می‌شود)
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/YOUR_USERNAME/sum-bot.git}"
BRANCH="${BRANCH:-main}"
DIR="${DIR:-/opt/sum-bot}"
SERVICE="sum-bot"

if [ "$(id -u)" -ne 0 ]; then
  echo "لطفاً با root اجرا کنید (sudo bash ...)"; exit 1
fi
if [[ "$REPO_URL" == *YOUR_USERNAME* ]]; then
  echo "اول در بالای install.sh مقدار REPO_URL را به آدرس مخزن خودتان تغییر دهید"
  echo "یا اجرا کنید: REPO_URL=https://github.com/نام/sum-bot.git bash install.sh"
  exit 1
fi

echo "==> نصب پیش‌نیازها"
apt-get update -y >/dev/null
apt-get install -y git python3 python3-venv python3-pip >/dev/null

BAK=""
if [ -d "$DIR" ] && [ ! -d "$DIR/.git" ]; then
  BAK="$DIR.bak.$(date +%s)"
  mv "$DIR" "$BAK"
  echo "==> پوشه‌ی قبلی به $BAK منتقل شد"
fi

if [ -d "$DIR/.git" ]; then
  echo "==> آپدیت کد"
  git -C "$DIR" fetch --quiet origin "$BRANCH"
  git -C "$DIR" reset --hard --quiet "origin/$BRANCH"
else
  echo "==> دریافت کد"
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$DIR"
fi

# برگرداندن تنظیمات و دیتابیس از پوشه‌ی قبلی (اگر بود)
if [ -n "$BAK" ]; then
  for f in .env data.db; do [ -f "$BAK/$f" ] && cp "$BAK/$f" "$DIR/$f"; done
fi

echo "==> ساخت venv و نصب کتابخانه"
[ -x "$DIR/venv/bin/python" ] || python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --upgrade pip
"$DIR/venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

if [ ! -f "$DIR/.env" ]; then
  echo "==> تنظیمات (فقط یک بار پرسیده می‌شود)"
  TOKEN=""
  while [ -z "$TOKEN" ]; do
    read -r -s -p "توکن ربات (از BotFather): " TOKEN < /dev/tty; echo
  done
  read -r -p "آیدی عددی گروه، مثل -100123... (می‌توانید خالی بگذارید): " CHAT < /dev/tty || true
  read -r -p "آیدی تاپیک [1]: " TOPIC < /dev/tty || true
  read -r -p "آیدی عددی خودتان (برای قفل روی شما؛ با /myid می‌گیرید، خالی هم می‌شود): " OWNER < /dev/tty || true
  umask 077
  printf 'BOT_TOKEN=%s\nCHAT_ID=%s\nTOPIC_ID=%s\nOWNER_IDS=%s\n' \
    "$TOKEN" "${CHAT:-}" "${TOPIC:-1}" "${OWNER:-}" > "$DIR/.env"
fi
chmod 600 "$DIR/.env"

echo "==> ساخت سرویس"
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
  echo "✅ ربات روشن است."
else
  echo "❌ سرویس بالا نیامد. لاگ:"; journalctl -u "$SERVICE" -n 20 --no-pager
  exit 1
fi
echo "لاگ زنده:  journalctl -u $SERVICE -f"
echo "تنظیمات:   nano $DIR/.env  (بعد: systemctl restart $SERVICE)"

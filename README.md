# PasarGuard Calculator (Sum Bot)

A Telegram bot that sums the **Data Limit** of users created by the [PasarGuard](https://github.com/PasarGuard/panel) panel
(`#Create_User` notifications), grouped by **Belongs To**. It gives you weekly and all-time reports.
The Iranian week is closed automatically every **Friday at 23:59 (Tehran time)**.

Example report:

```
📅 Week 1 (1405/08/11 to 1405/08/15)
━━━━━━━━━━━━━━━
👤 MSN — 2 users — 90 GB
   • Bijan — 60 GB
   • Ali — 30 GB
━━━━━━━━━━━━━━━
📊 Total: 140 GB
```

## Requirements

- A server with Ubuntu/Debian and root access (SSH) — the same server as your panel works fine
- A Telegram group (with a topic if you use topics)
- PasarGuard's Telegram notifications sending into that group/topic

## Install

**1. Create a NEW bot** in [@BotFather](https://t.me/BotFather) with `/newbot` and copy the token.
Do not reuse the token of the PasarGuard bot.

**2. Collect these values** (the installer will ask for them):

| Value | What it is |
|---|---|
| Bot token | From @BotFather |
| Group chat ID | Numeric ID of your group, starts with `-100` (e.g. `-1001234567890`). Open the group in web.telegram.org and read it from the URL, or forward a message to @getidsbot |
| Topic ID | Topic to watch. `1` = General topic |
| Your user ID | Your numeric Telegram ID. Only this user can use the bot. Send `/myid` to the bot to get it (you can skip this at first) |

**3. Run on your server** (SSH, as root). Do **not** run it from inside `/opt/sum-bot`:

```bash
cd /
bash <(curl -fsSL https://raw.githubusercontent.com/iLiYAMlPF/PasarGuard-Calculator/main/install.sh)
```

The script installs everything, asks the 4 questions above, creates a systemd service and starts the bot.
At the end you should see `✅ Bot is running.`

**4. Telegram settings** (required, otherwise the bot cannot see PasarGuard's messages):

1. Add the bot to your group and make it an **admin**.
2. In @BotFather: `/setprivacy` → choose the bot → **Disable**. Then remove the bot from the group and add it again (and make it admin again).
3. In @BotFather: enable **Bot-to-Bot Communication Mode** for **both** bots (PasarGuard's bot and this one).

**5. Test**

- Send `/week` in the topic — the bot should answer.
- Create a user in the panel — the bot should react with 👍 to PasarGuard's message.

## Commands

| Command | Description |
|---|---|
| `/week` | Report for the current week (not closed yet) and the next automatic close time |
| `/week 3` | Report for closed week number 3 |
| `/closeweek` | Close the current week manually (asks for confirmation) |
| `/total` | All-time total |
| `/weeks` | List of closed weeks |
| `/myid` | Shows your numeric Telegram ID |

Add `short` or `full` to a report command, e.g. `/total full` or `/week short`.

After a week is closed (manually or automatically) it is no longer included in `/week`; counting starts from zero for the new week.
Closed weeks stay in `/total` and `/weeks`.

## Configuration

Edit `/opt/sum-bot/.env`, then run `systemctl restart sum-bot`.

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | Bot token (required) |
| `CHAT_ID` | empty | Group ID. Empty = works in any group the bot is added to |
| `TOPIC_ID` | `1` | Topic to watch (`1` = General) |
| `OWNER_IDS` | empty | Comma-separated user IDs allowed to use commands. Empty = everyone can view reports, only group admins can close weeks |
| `AUTO_CLOSE` | `1` | `0` disables the automatic weekly close |
| `WEEK_END_DAY` | `fri` | `sat sun mon tue wed thu fri` |
| `WEEK_END_TIME` | `23:59` | Time (Tehran) of the automatic close |
| `TIMEZONE` | `Asia/Tehran` | Timezone used for week boundaries and dates |
| `COUNT_TAGS` | `#Create_User` | Which PasarGuard notifications are counted |
| `REPLY_EACH` | `0` | `1` = reply to every counted message |
| `REACT` | `1` | `1` = react with 👍 to counted messages |

## Update

Run the install command again. The code is updated; `.env` and `data.db` are kept.

## Uninstall

```bash
systemctl stop sum-bot && systemctl disable sum-bot
rm /etc/systemd/system/sum-bot.service && systemctl daemon-reload
rm -rf /opt/sum-bot
```

## Troubleshooting

```bash
systemctl status sum-bot
journalctl -u sum-bot -n 50 --no-pager
```

- **`203/EXEC` in the logs** — the virtualenv is missing; run the install command again.
- **Bot answers `/myid` but ignores PasarGuard messages** — check step 4 (admin, privacy disabled, Bot-to-Bot Mode on both bots).
- **Nothing answers in the group** — check `CHAT_ID` (must include the minus sign and `-100`), `TOPIC_ID` and `OWNER_IDS`.

> ⚠️ Never commit your `.env` file or bot token to GitHub. If a token leaks, revoke it with `/revoke` in @BotFather.

---

## خلاصه‌ی فارسی

ربات تلگرام برای جمع زدن حجم (Data Limit) کاربران ساخته‌شده در پنل پاسارگارد، به تفکیک `Belongs To`، با گزارش هفتگی و جمع کل.
هفته‌ی ایرانی هر جمعه ساعت ۲۳:۵۹ (وقت تهران) خودکار بسته می‌شود.

**نصب:** یک ربات جدید در @BotFather بسازید، بعد روی سرور (به‌جز داخل پوشه‌ی `/opt/sum-bot`) این را اجرا کنید و به ۴ سؤال جواب بدهید (توکن، آیدی گروه، آیدی تاپیک، آیدی عددی خودتان):

```bash
cd /
bash <(curl -fsSL https://raw.githubusercontent.com/iLiYAMlPF/PasarGuard-Calculator/main/install.sh)
```

بعد ربات را ادمین گروه کنید، `/setprivacy` را Disable کنید و Bot-to-Bot Communication Mode را برای هر دو ربات (پاسارگارد و این ربات) در @BotFather روشن کنید.

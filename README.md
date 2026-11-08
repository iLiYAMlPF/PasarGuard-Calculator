# PasarGuard Calculator (Sum Bot)

🇮🇷 **[توضیحات کامل فارسی (Persian README)](README.fa.md)**

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
| `/analyze` | Full analysis: totals, averages, share of each owner, biggest accounts, weekly list |
| `/analyze help` | How to import old messages |
| `/price` | Show prices. `/price MSN 1500` = toman per GB for one *Belongs To*, `/price all 1000` = default, `/price MSN off` = remove |
| `/userprice Ali 90000` | Fixed price for one username (overrides the per-GB price) |
| `/sales` | Sales in toman per *Belongs To*: current week; `/sales 3` a closed week; `/sales total` everything; add `full` for per-user lines |
| `/add Ali 30 MSN` | Add a record manually (username, size, Belongs To) |
| `/remove Ali` | Remove a record (shows buttons to pick which one) |
| `/backup` | Sends a backup of the database (private chat only) |
| `/status` | Diagnostics: IDs, admin rights, whether PasarGuard messages are seen |
| `/help` | Command list |
| `/version` | Shows the installed bot version |
| `/update` | Checks GitHub for a new version and updates the bot (owner only). `/update force` updates even if the version number is the same |
| `/myid` | Shows your numeric Telegram ID |

Add `short` or `full` to a report command, e.g. `/total full` or `/week short`.

After a week is closed (manually or automatically) it is no longer included in `/week`; counting starts from zero for the new week.
Closed weeks stay in `/total` and `/weeks`.

## Analyze old messages

Telegram bots **cannot read old group messages**, so history must be imported once from a chat export:

1. On **Telegram Desktop** (computer) open the group → ⋮ menu → **Export chat history**.
2. Turn off all media (photos, videos, files…) so only messages are exported.
3. Set the format to **Machine-readable JSON** and export.
4. Send the resulting `result.json` to the bot in a **private chat** (requires `OWNER_IDS` to be set).

The bot reads every `#Create_User` message, splits them into the correct Iranian weeks (closed weeks + the current open week) and replies with a full analysis.
Re-sending the same file is safe: already-known messages are skipped. Week numbers are re-sorted by date after an import.
Use `/analyze` any time later to see the analysis again. Files up to 20 MB are supported.

## Prices and sales

1. Set a price per GB: `/price MSN 1500` (for one *Belongs To*) or `/price all 1000` (default for everyone else).
2. Optional fixed price for a single user: `/userprice Ali 90000`.
3. `/sales` shows how many toman each *Belongs To* sold. When prices exist, the sales report is also sent automatically after every weekly close.

## Backup and restore

- `/backup` in a private chat sends you the database file. With `AUTO_BACKUP=1` a backup is also sent after every automatic weekly close.
- **Restore:** send that `.db` file to the bot in a private chat and press **Restore**. A safety copy of the current data is saved next to the database first.
- The backup contains no token (the token lives only in `.env`).

## Troubleshooting: the bot does not record new users

Send `/status` **inside the topic where PasarGuard posts**. It shows the chat and topic ID, whether the bot is admin and can delete messages, and whether it has seen a `#Create_User` message (and why it was ignored). If PasarGuard posts to a **channel**, add the bot to the channel as an admin.

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
| `UPDATE_CHECK` | `1` | Check GitHub every 12 h and message the owners when a new version exists |
| `VERSION_URL` | repo's raw `VERSION` | Where the latest version number is read from |
| `UPDATE_BRANCH` | `main` | Branch used by `/update` |
| `DELETE_PATTERNS` | `User not found` | Messages containing these texts are deleted (separate several with `|`, empty = off). The bot must be admin with *Delete messages* |
| `AUTO_BACKUP` | `1` | Send a backup to the owners (private chat) after every automatic weekly close |
| `CURRENCY` | `تومان` | Currency label in sales reports |
| `REPLY_EACH` | `0` | `1` = reply to every counted message |
| `REACT` | `1` | `1` = react with 👍 to counted messages |

## Update

### Publishing a new version (you, on GitHub)
1. Edit the files in the repository (e.g. `sum_bot.py`).
2. Change the number in the `VERSION` file (e.g. `1.0.0` → `1.1.0`).
3. Optionally describe the change in `CHANGELOG.md`.
4. Commit to the `main` branch.

### Updating the server
Pick one:

- **From the server:** `sum-bot update`
- **From Telegram:** send `/update` to the bot (private chat, owner only), then press **Update**.
  If `UPDATE_CHECK=1` the bot also messages you by itself when a new version appears
  (start the bot once in a private chat so it is allowed to write to you).
- **Re-run the installer:** the same command as the install step.

Your `.env` and `data.db` are always kept. The bot restarts for a few seconds.

> Servers installed before the update system existed need to run the install command **once** to get the `sum-bot` command and `/update`.

### The `sum-bot` command

| Command | Description |
|---|---|
| `sum-bot update` | Download the latest version and restart |
| `sum-bot version` | Show the installed version |
| `sum-bot status` | Service status |
| `sum-bot logs` | Live logs |
| `sum-bot restart` | Restart the bot |
| `sum-bot config` | Edit `.env` and restart |
| `sum-bot uninstall` | Remove the bot (keeps a DB backup in `/root`) |

## Uninstall

```bash
sum-bot uninstall
```

It asks for confirmation and saves a database backup to `/root/sum-bot-data.db.bak`.

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

🇮🇷 توضیحات کامل فارسی: [README.fa.md](README.fa.md)

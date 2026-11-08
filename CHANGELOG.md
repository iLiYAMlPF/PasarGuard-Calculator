# Changelog

## 1.1.0
- Prices and sales: `/price`, `/userprice`, `/sales` (toman per Belongs To)
- Backup and restore: `/backup`, send a `.db` file to restore, automatic backup after each weekly close
- Manual `/add` and `/remove`
- Channel posts are now recorded (not only group messages)
- `/status` diagnostics (chat/topic IDs, admin rights, whether PasarGuard messages are seen) and `/help`
- "User not found" cleanup now works in the whole group, not only in one topic

## 1.0.1
- Auto-delete unwanted bot messages such as "User not found!" (`DELETE_PATTERNS`)

## 1.0.0
- Sum PasarGuard `#Create_User` data limits per `Belongs To`
- Weekly reports, all-time totals, automatic weekly close (Friday 23:59 Tehran)
- `/analyze` and import of old messages from a Telegram JSON export
- Owner-only mode (`OWNER_IDS`)
- Update system: `sum-bot update` on the server and `/update` inside Telegram

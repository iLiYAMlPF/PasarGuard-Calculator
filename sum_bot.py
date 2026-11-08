"""
ربات جمع حجم کاربران پاسارگارد (گزارش کل و هفتگی) برای تاپیک گروه تلگرام

ربات پیام‌های #Create_User را بی‌صدا ثبت می‌کند (فقط یک 👍 می‌زند).
هر وقت خودتان خواستید گزارش بگیرید یا هفته را ببندید:

    /week            گزارش هفته‌ی جاری (هنوز بسته نشده)
    /week 3          گزارش هفته‌ی بسته‌شده‌ی شماره ۳
    /closeweek       بستن هفته (فقط ادمین) -> هفته‌ی بعد از صفر شروع می‌شود
    /total           جمع کل همه‌ی هفته‌ها (خلاصه)
    /weeks           فهرست هفته‌های بسته‌شده
    بستن خودکار: هر هفته جمعه 23:59 به وقت تهران (قابل تغییر با WEEK_END_DAY و WEEK_END_TIME)
    /analyze         تحلیل کامل (جمع، میانگین، سهم هر Belongs To، بزرگ‌ترین اکانت‌ها)
    /analyze help    آموزش ایمپورت پیام‌های قدیمی (فایل result.json را در پیوی ربات بفرستید)
    /version         نسخه‌ی ربات
    /update          بررسی و آپدیت ربات از GitHub (فقط OWNER_IDS)؛ /update force برای آپدیت اجباری
    /sales [شماره|total] [full]   فروش به تومان (بعد از تعیین قیمت)
    /price [owner|all مبلغ]       قیمت هر گیگ؛ /userprice نام مبلغ = قیمت ثابت یک کاربر
    /add نام حجم owner            افزودن دستی؛ /remove نام = حذف
    /backup                       بکاپ دیتابیس (پیوی)؛ فایل .db را بفرستید تا ریستور شود
    /status                       عیب‌یابی؛ /help راهنما
    /myid            آیدی عددی خودتان (برای تنظیم OWNER_IDS)
    به همه‌ی گزارش‌ها می‌توانید short (خلاصه) یا full (کامل) اضافه کنید

نصب:   pip install "python-telegram-bot>=21"
اجرا:  BOT_TOKEN=... TOPIC_ID=1 OWNER_IDS=123456789 python3 sum_bot.py

نکته: تلگرام پیام ربات‌ها را به ربات‌های دیگر نمی‌دهد. در @BotFather برای هر دو
ربات (پاسارگارد و این ربات) Bot-to-Bot Communication Mode را روشن کنید،
این ربات را ادمین گروه کنید و Group Privacy را Disable کنید.
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReactionTypeEmoji,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))  # 0 یعنی هر گروهی
TOPIC_ID = int(os.getenv("TOPIC_ID", "1"))
DB_PATH = os.getenv("DB_PATH", "data.db")
REPLY_EACH = os.getenv("REPLY_EACH", "0") == "1"  # بعد از هر پیام جواب کوتاه بدهد؟
REACT = os.getenv("REACT", "1") == "1"  # روی پیام ثبت‌شده 👍 بزند؟
# آیدی عددی کسانی که اجازه‌ی استفاده از دستورها را دارند (با کاما جدا کنید).
# اگر خالی باشد: همه می‌توانند گزارش ببینند و فقط ادمین‌ها هفته را می‌بندند.
OWNER_IDS = {
    int(x) for x in os.getenv("OWNER_IDS", "").replace(" ", "").split(",") if x.lstrip("-").isdigit()
}
# بستن خودکار هفته: پیش‌فرض آخر هفته‌ی ایرانی (جمعه ساعت 23:59 به وقت تهران)
AUTO_CLOSE = os.getenv("AUTO_CLOSE", "1") == "1"
WEEK_END_DAY = os.getenv("WEEK_END_DAY", "fri").lower()  # sat sun mon tue wed thu fri
WEEK_END_TIME = os.getenv("WEEK_END_TIME", "23:59")
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DAY_FA = {0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنجشنبه", 4: "جمعه", 5: "شنبه", 6: "یکشنبه"}
# پیام‌هایی که ربات حذف می‌کند (چند عبارت را با | جدا کنید؛ خالی = خاموش). ربات باید ادمین با دسترسی Delete messages باشد
DELETE_PATTERNS = [
    x.strip().lower() for x in os.getenv("DELETE_PATTERNS", "User not found").split("|") if x.strip()
]
COUNT_TAGS = {
    t.strip().lower()
    for t in os.getenv("COUNT_TAGS", "#Create_User").split(",")
    if t.strip()
}

# آپدیت از GitHub
APP_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_NAME = os.getenv("SERVICE_NAME", "sum-bot")
UPDATE_BRANCH = os.getenv("UPDATE_BRANCH", "main")
VERSION_URL = os.getenv(
    "VERSION_URL",
    "https://raw.githubusercontent.com/iLiYAMlPF/PasarGuard-Calculator/main/VERSION",
)
UPDATE_CHECK = os.getenv("UPDATE_CHECK", "1") == "1"  # هر ۱۲ ساعت نسخه‌ی جدید را چک کند و به OWNER_IDS خبر بدهد
AUTO_BACKUP = os.getenv("AUTO_BACKUP", "1") == "1"  # بعد از هر بستن خودکار هفته، بکاپ به پیوی مالک‌ها برود
CURRENCY = os.getenv("CURRENCY", "تومان")
RESTORE_TMP = os.getenv("DB_PATH", "data.db") + ".restore"

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tehran"))
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=3, minutes=30))

UNITS = {"MB": 1 / 1024, "GB": 1.0, "TB": 1024.0}
LIMIT_RE = re.compile(r"Data\s*Limit\s*:\s*(\d+(?:[.,]\d+)?)\s*(MB|GB|TB)", re.I)
OWNER_RE = re.compile(r"Belongs\s*To\s*:\s*([^\n\r]+)", re.I)
BY_RE = re.compile(r"\bBy\s*:\s*#?([^\s\n\r]+)", re.I)
USER_RE = re.compile(r"Username\s*:\s*([^\s\n\r]+)", re.I)
TAG_RE = re.compile(r"#\w+_User\b", re.I)
SEP = "━━━━━━━━━━━━━━━"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sum_bot")


# ---------- تاریخ شمسی ----------
def g2j(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy, gy = 979, gy - 1600
    else:
        jy, gy = 0, gy - 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
        - 80 + gd + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def fmt_date(iso: str) -> str:
    d = datetime.fromisoformat(iso).astimezone(TZ)
    jy, jm, jd = g2j(d.year, d.month, d.day)
    return f"{jy}/{jm:02d}/{jd:02d}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- پارس پیام ----------
def parse_message(text: str):
    """لیست (gb, owner, account) برمی‌گرداند. اگر چیزی پیدا نشد لیست خالی."""
    tag = TAG_RE.search(text)
    if tag and tag.group(0).lower() not in COUNT_TAGS:
        return []
    limits = list(LIMIT_RE.finditer(text))
    results = []
    for i, m in enumerate(limits):
        start = limits[i - 1].end() if i else 0
        end = limits[i + 1].start() if i + 1 < len(limits) else len(text)
        gb = float(m.group(1).replace(",", ".")) * UNITS[m.group(2).upper()]
        owner_m = OWNER_RE.search(text, m.end(), end) or BY_RE.search(text, m.end(), end)
        owner = owner_m.group(1).strip() if owner_m else "نامشخص"
        user_m = USER_RE.search(text, start, end)
        account = user_m.group(1) if user_m else "-"
        results.append((gb, owner, account))
    return results


def should_delete(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in DELETE_PATTERNS)


def fmt_gb(x: float) -> str:
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return f"{s} GB"


# ---------- دیتابیس ----------
def db():
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS entries (
            chat_id INTEGER, message_id INTEGER, idx INTEGER,
            sender_id INTEGER, sender_name TEXT,
            owner TEXT, gb REAL, account TEXT,
            week_id INTEGER, created_at TEXT,
            PRIMARY KEY (chat_id, message_id, idx))"""
    )
    for col, typ in (("account", "TEXT"), ("week_id", "INTEGER"), ("created_at", "TEXT")):
        try:  # برای دیتابیس نسخه‌های قبلی
            con.execute(f"ALTER TABLE entries ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    con.execute(
        """CREATE TABLE IF NOT EXISTS weeks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, number INTEGER,
            started_at TEXT, closed_at TEXT, total_gb REAL, count INTEGER)"""
    )
    con.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, thread_id INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
    con.execute(
        "CREATE TABLE IF NOT EXISTS prices (chat_id INTEGER, owner TEXT, per_gb REAL, PRIMARY KEY (chat_id, owner))"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS user_prices (chat_id INTEGER, account TEXT, price REAL, PRIMARY KEY (chat_id, account))"
    )
    return con


def remember_chat(chat_id, thread_id):
    con = db()
    with con:
        con.execute("INSERT OR REPLACE INTO chats (chat_id, thread_id) VALUES (?,?)", (chat_id, thread_id))
    con.close()


def get_state(key):
    con = db()
    r = con.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    con.close()
    return r[0] if r else None


def set_state(key, value):
    con = db()
    with con:
        con.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?,?)", (key, value))
    con.close()


def save_entries(chat_id, message_id, sender_id, sender_name, items, created_at):
    """False برمی‌گرداند اگر این پیام قبلاً در یک هفته‌ی بسته‌شده ثبت شده باشد."""
    con = db()
    try:
        locked = con.execute(
            "SELECT 1 FROM entries WHERE chat_id=? AND message_id=? AND week_id IS NOT NULL",
            (chat_id, message_id),
        ).fetchone()
        if locked:
            return False
        with con:
            con.execute(
                "DELETE FROM entries WHERE chat_id=? AND message_id=? AND week_id IS NULL",
                (chat_id, message_id),
            )
            for idx, (gb, owner, account) in enumerate(items):
                con.execute(
                    "INSERT INTO entries (chat_id, message_id, idx, sender_id, sender_name,"
                    " owner, gb, account, week_id, created_at) VALUES (?,?,?,?,?,?,?,?,NULL,?)",
                    (chat_id, message_id, idx, sender_id, sender_name, owner, gb, account, created_at),
                )
        return True
    finally:
        con.close()


def get_rows(chat_id, scope):
    """scope: 'open' | 'all' | week_id (int). خروجی: [(owner, account, gb, created_at)]"""
    con = db()
    q = "SELECT owner, account, gb, created_at FROM entries WHERE chat_id=?"
    args = [chat_id]
    if scope == "open":
        q += " AND week_id IS NULL"
    elif scope != "all":
        q += " AND week_id=?"
        args.append(scope)
    rows = con.execute(q + " ORDER BY created_at", args).fetchall()
    con.close()
    return rows


def get_week(chat_id, number):
    con = db()
    row = con.execute(
        "SELECT id, number, started_at, closed_at, total_gb, count FROM weeks"
        " WHERE chat_id=? AND number=?",
        (chat_id, number),
    ).fetchone()
    con.close()
    return row


def list_weeks(chat_id):
    con = db()
    rows = con.execute(
        "SELECT id, number, started_at, closed_at, total_gb, count FROM weeks"
        " WHERE chat_id=? ORDER BY number",
        (chat_id,),
    ).fetchall()
    con.close()
    return rows


def next_week_number(chat_id) -> int:
    con = db()
    n = con.execute("SELECT MAX(number) FROM weeks WHERE chat_id=?", (chat_id,)).fetchone()[0]
    con.close()
    return (n or 0) + 1


def close_week(chat_id, until=None):
    """هفته‌ی باز را می‌بندد (اگر until داده شود فقط ثبت‌های تا آن لحظه).
    اگر چیزی برای بستن نباشد None برمی‌گرداند."""
    con = db()
    cond = " AND (created_at IS NULL OR created_at <= ?)" if until else ""
    extra = (until,) if until else ()
    closed_at = until or now_iso()
    try:
        with con:
            rows = con.execute(
                "SELECT gb, created_at FROM entries WHERE chat_id=? AND week_id IS NULL" + cond,
                (chat_id, *extra),
            ).fetchall()
            if not rows:
                return None
            number = (
                con.execute("SELECT MAX(number) FROM weeks WHERE chat_id=?", (chat_id,)).fetchone()[0]
                or 0
            ) + 1
            started = min(r[1] for r in rows if r[1]) if any(r[1] for r in rows) else now_iso()
            total = sum(r[0] for r in rows)
            cur = con.execute(
                "INSERT INTO weeks (chat_id, number, started_at, closed_at, total_gb, count)"
                " VALUES (?,?,?,?,?,?)",
                (chat_id, number, started, closed_at, total, len(rows)),
            )
            con.execute(
                "UPDATE entries SET week_id=? WHERE chat_id=? AND week_id IS NULL" + cond,
                (cur.lastrowid, chat_id, *extra),
            )
            return {"id": cur.lastrowid, "number": number, "started": started,
                    "closed": closed_at, "total": total, "count": len(rows)}
    finally:
        con.close()


# ---------- ساخت گزارش ----------
def chunk_text(text: str, limit: int = 3800):
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            parts.append(cur.rstrip())
            cur = ""
        cur += line + "\n"
    if cur.strip():
        parts.append(cur.rstrip())
    return parts


def build_report(title, rows, short=False, note=None):
    if not rows:
        return [f"{title}\n{SEP}\nهنوز چیزی ثبت نشده."]
    groups = defaultdict(list)
    for owner, account, gb, _ in rows:
        groups[owner].append((account, gb))
    order = sorted(groups.items(), key=lambda kv: -sum(g for _, g in kv[1]))
    total = sum(r[2] for r in rows)

    lines = [title]
    if note:
        lines.append(note)
    lines.append(SEP)
    for owner, users in order:
        sub = sum(g for _, g in users)
        lines.append(f"👤 {owner} — {len(users)} کاربر — {fmt_gb(sub)}")
        if not short:
            for account, gb in sorted(users, key=lambda x: -x[1]):
                lines.append(f"   • {account} — {fmt_gb(gb)}")
            lines.append("")
    if lines[-1] == "":
        lines.pop()
    lines += [SEP, f"📊 جمع کل: {fmt_gb(total)}", f"👥 تعداد کاربر: {len(rows)}"]
    return chunk_text("\n".join(lines))


def last_boundary(now_local):
    """آخرین پایان هفته که تا الان گذشته (به وقت محلی)."""
    hh, mm = (int(x) for x in WEEK_END_TIME.split(":"))
    cand = now_local.replace(hour=hh, minute=mm, second=59, microsecond=0)
    cand -= timedelta(days=(cand.weekday() - DAYS.get(WEEK_END_DAY, 4)) % 7)
    if cand > now_local:
        cand -= timedelta(days=7)
    return cand


def next_boundary_text():
    nb = last_boundary(datetime.now(TZ)) + timedelta(days=7)
    jy, jm, jd = g2j(nb.year, nb.month, nb.day)
    return f"{DAY_FA[nb.weekday()]} {jy}/{jm:02d}/{jd:02d} ساعت {nb.strftime('%H:%M')}"


def open_title(chat_id, rows):
    n = next_week_number(chat_id)
    if rows and rows[0][3]:
        return f"📅 هفته‌ی جاری (شماره {n}) — از {fmt_date(rows[0][3])} تا امروز"
    return f"📅 هفته‌ی جاری (شماره {n})"


def closed_title(number, started, closed):
    return f"📅 هفته {number} ({fmt_date(started)} تا {fmt_date(closed)})"


# ---------- ایمپورت تاریخچه و تحلیل ----------
HOWTO_IMPORT = (
    "📥 تحلیل پیام‌های قدیمی\n\n"
    "ربات‌های تلگرام نمی‌توانند پیام‌های قدیمی گروه را بخوانند، پس یک بار باید از گروه خروجی بگیرید:\n"
    "1. در Telegram Desktop (کامپیوتر) گروه را باز کنید\n"
    "2. منوی ⋮ بالای صفحه ← Export chat history\n"
    "3. همه‌ی گزینه‌های رسانه (عکس، ویدیو، فایل...) را خاموش کنید و فقط پیام‌ها بماند\n"
    "4. Format را روی Machine-readable JSON بگذارید\n"
    "5. Export را بزنید و فایل result.json را در پیوی همین ربات بفرستید\n\n"
    "ربات پیام‌های #Create_User را می‌خواند، به هفته‌ها تقسیم می‌کند و تحلیل کامل می‌فرستد. "
    "فرستادن دوباره‌ی فایل مشکلی ندارد، پیام تکراری شمرده نمی‌شود.\n"
    "(برای ایمپورت باید OWNER_IDS در .env تنظیم شده باشد.)"
)


def flatten_text(t):
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        return "".join(x if isinstance(x, str) else str(x.get("text", "")) for x in t)
    return ""


def week_end_utc(dt_utc):
    """اولین پایان هفته‌ای که برابر یا بعد از dt است (UTC)."""
    local = dt_utc.astimezone(TZ)
    b = last_boundary(local)
    if b < local:
        b = b + timedelta(days=7)
    return b.astimezone(timezone.utc)


def export_chat_id(obj):
    if CHAT_ID:
        return CHAT_ID
    cid, t = obj.get("id"), str(obj.get("type", ""))
    if cid is None:
        return None
    return int(f"-100{cid}") if ("supergroup" in t or "channel" in t) else -int(cid)


def import_history(obj):
    """خروجی JSON تلگرام دسکتاپ را وارد دیتابیس می‌کند و ثبت‌ها را به هفته‌ها تقسیم می‌کند."""
    if not isinstance(obj, dict) or "messages" not in obj:
        return {"error": "این فایل خروجی یک گروه نیست. فقط همان گروه را Export کنید (نه کل اکانت)."}
    chat_id = export_chat_id(obj)
    if chat_id is None:
        return {"error": "آیدی گروه در فایل پیدا نشد. CHAT_ID را در .env بگذارید."}
    now_b = last_boundary(datetime.now(TZ)).astimezone(timezone.utc)

    con = db()
    try:
        existing = {
            r[0] for r in con.execute("SELECT DISTINCT message_id FROM entries WHERE chat_id=?", (chat_id,))
        }
        found = skipped = added = open_added = 0
        parsed = []
        for m in obj["messages"]:
            if m.get("type") != "message":
                continue
            items = parse_message(flatten_text(m.get("text")))
            if not items:
                continue
            found += 1
            mid = m.get("id")
            if mid is None or mid in existing:
                skipped += 1
                continue
            try:
                ts = m.get("date_unixtime")
                if ts:
                    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                else:
                    dt = datetime.fromisoformat(m["date"]).replace(tzinfo=TZ).astimezone(timezone.utc)
            except Exception:  # noqa: BLE001
                skipped += 1
                continue
            parsed.append((mid, dt, str(m.get("from") or ""), items))

        affected = set()
        with con:
            for mid, dt, sender, items in parsed:
                week_id = None
                if dt <= now_b:
                    wend = week_end_utc(dt).isoformat()
                    row = con.execute(
                        "SELECT id FROM weeks WHERE chat_id=? AND closed_at=?", (chat_id, wend)
                    ).fetchone()
                    if row:
                        week_id = row[0]
                    else:
                        week_id = con.execute(
                            "INSERT INTO weeks (chat_id, number, started_at, closed_at, total_gb, count)"
                            " VALUES (?,?,?,?,?,?)",
                            (chat_id, 0, dt.isoformat(), wend, 0, 0),
                        ).lastrowid
                    affected.add(week_id)
                else:
                    open_added += len(items)
                for idx, (gb, owner, account) in enumerate(items):
                    con.execute(
                        "INSERT INTO entries (chat_id, message_id, idx, sender_id, sender_name,"
                        " owner, gb, account, week_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (chat_id, mid, idx, 0, sender, owner, gb, account, week_id, dt.isoformat()),
                    )
                    added += 1
            for wid in affected:
                tot, cnt, first = con.execute(
                    "SELECT COALESCE(SUM(gb),0), COUNT(*), MIN(created_at) FROM entries WHERE week_id=?",
                    (wid,),
                ).fetchone()
                con.execute(
                    "UPDATE weeks SET total_gb=?, count=?, started_at=? WHERE id=?", (tot, cnt, first, wid)
                )
            ids = [
                r[0]
                for r in con.execute("SELECT id FROM weeks WHERE chat_id=? ORDER BY closed_at, id", (chat_id,))
            ]
            for n, wid in enumerate(ids, 1):
                con.execute("UPDATE weeks SET number=? WHERE id=?", (n, wid))
            con.execute(
                "INSERT OR IGNORE INTO chats (chat_id, thread_id) VALUES (?,?)",
                (chat_id, None if TOPIC_ID == 1 else TOPIC_ID),
            )
        return {
            "chat_id": chat_id,
            "found": found,
            "skipped": skipped,
            "added": added,
            "weeks": len(affected),
            "open_added": open_added,
        }
    finally:
        con.close()


def build_analysis(chat_id):
    rows = get_rows(chat_id, "all")
    if not rows:
        return None
    total = sum(r[2] for r in rows)
    n = len(rows)
    safe_total = total or 1
    dates = sorted(r[3] for r in rows if r[3])
    weeks = list_weeks(chat_id)
    open_rows = get_rows(chat_id, "open")
    open_total = sum(r[2] for r in open_rows)

    lines = ["🔍 تحلیل کامل", SEP]
    if dates:
        lines.append(f"🗓 بازه: {fmt_date(dates[0])} تا {fmt_date(dates[-1])}")
    lines += [
        f"📊 جمع کل: {fmt_gb(total)}",
        f"👥 تعداد کاربر: {n}",
        f"📈 میانگین هر کاربر: {fmt_gb(total / n)}",
    ]
    week_list = [(f"هفته {w[1]}", w[4], w[5]) for w in weeks]
    if open_rows:
        week_list.append(("هفته‌ی جاری", open_total, len(open_rows)))
    if week_list:
        lines.append(f"🗓 میانگین هر هفته: {fmt_gb(total / len(week_list))}")
        peak = max(week_list, key=lambda x: x[1])
        lines.append(f"🏆 پرحجم‌ترین هفته: {peak[0]} — {fmt_gb(peak[1])}")

    by_owner = defaultdict(lambda: [0.0, 0])
    for owner, _, gb, _ in rows:
        by_owner[owner][0] += gb
        by_owner[owner][1] += 1
    lines += ["", "👤 به تفکیک Belongs To:"]
    for owner, (gb, cnt) in sorted(by_owner.items(), key=lambda kv: -kv[1][0]):
        lines.append(
            f"• {owner}: {fmt_gb(gb)} ({gb / safe_total * 100:.0f}%) — {cnt} کاربر — میانگین {fmt_gb(gb / cnt)}"
        )

    lines += ["", "🏅 بزرگ‌ترین اکانت‌ها:"]
    for owner, account, gb, _ in sorted(rows, key=lambda r: -r[2])[:5]:
        lines.append(f"• {account} — {fmt_gb(gb)} ({owner})")

    if week_list:
        lines += ["", "🗂 هفته‌ها (آخرین ۱۲ مورد):"]
        for label, gb, cnt in week_list[-12:]:
            lines.append(f"• {label}: {fmt_gb(gb)} — {cnt} کاربر")
        if len(week_list) > 12:
            lines.append(f"(+{len(week_list) - 12} هفته‌ی قدیمی‌تر، با /weeks)")
    lines += [SEP, "برای پیام‌های قدیمی‌تر: /analyze help"]
    return chunk_text("\n".join(lines))


def single_known_chat():
    con = db()
    rows = con.execute("SELECT chat_id FROM chats").fetchall()
    con.close()
    return rows[0][0] if len(rows) == 1 else None


# ---------- آپدیت ----------
def local_version() -> str:
    try:
        with open(os.path.join(APP_DIR, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def vtuple(v: str):
    nums = [int(x) for x in re.findall(r"\d+", v or "")][:3]
    return tuple(nums + [0] * (3 - len(nums)))


def fetch_latest_version():
    try:
        with urllib.request.urlopen(VERSION_URL, timeout=10) as r:
            return r.read().decode("utf-8").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("version check failed: %s", e)
        return None


def run_update():
    if not os.path.isdir(os.path.join(APP_DIR, ".git")):
        return False, "این نصب با git انجام نشده. روی سرور از دستور sum-bot update یا install.sh استفاده کنید."
    steps = [
        ["git", "-C", APP_DIR, "fetch", "--quiet", "origin", UPDATE_BRANCH],
        ["git", "-C", APP_DIR, "reset", "--hard", "--quiet", f"origin/{UPDATE_BRANCH}"],
        [sys.executable, "-m", "pip", "install", "--quiet", "-r", os.path.join(APP_DIR, "requirements.txt")],
    ]
    for cmd in steps:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except Exception as e:  # noqa: BLE001
            return False, str(e)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "unknown error")
    return True, ""


def owner_only(update: Update) -> bool:
    u = update.effective_user
    return bool(OWNER_IDS and u and u.id in OWNER_IDS)


# ---------- پول و فروش ----------
def money(x: float) -> str:
    return f"{x:,.0f} {CURRENCY}"


def parse_number(txt):
    t = str(txt).replace(",", "").replace("٬", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def parse_size(txt):
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*(mb|gb|tb)?$", txt.strip(), re.I)
    if not m:
        return None
    return float(m.group(1).replace(",", ".")) * UNITS[(m.group(2) or "GB").upper()]


def get_prices(chat_id):
    """(قیمت پیش‌فرض هر گیگ, {owner_lower: per_gb}, {account_lower: price})"""
    con = db()
    default, owners, users = None, {}, {}
    for owner, per_gb in con.execute("SELECT owner, per_gb FROM prices WHERE chat_id=?", (chat_id,)):
        if owner == "*":
            default = per_gb
        else:
            owners[owner.lower()] = per_gb
    for account, price in con.execute("SELECT account, price FROM user_prices WHERE chat_id=?", (chat_id,)):
        users[account.lower()] = price
    con.close()
    return default, owners, users


def list_prices(chat_id):
    con = db()
    owners = con.execute(
        "SELECT owner, per_gb FROM prices WHERE chat_id=? AND owner<>'*' ORDER BY owner", (chat_id,)
    ).fetchall()
    users = con.execute(
        "SELECT account, price FROM user_prices WHERE chat_id=? ORDER BY account", (chat_id,)
    ).fetchall()
    con.close()
    return owners, users


def set_owner_price(chat_id, owner, per_gb):
    con = db()
    with con:
        con.execute("DELETE FROM prices WHERE chat_id=? AND lower(owner)=lower(?)", (chat_id, owner))
        if per_gb is not None:
            con.execute("INSERT INTO prices (chat_id, owner, per_gb) VALUES (?,?,?)", (chat_id, owner, per_gb))
    con.close()


def set_user_price(chat_id, account, price):
    con = db()
    with con:
        con.execute("DELETE FROM user_prices WHERE chat_id=? AND lower(account)=lower(?)", (chat_id, account))
        if price is not None:
            con.execute(
                "INSERT INTO user_prices (chat_id, account, price) VALUES (?,?,?)", (chat_id, account, price)
            )
    con.close()


def has_prices(chat_id) -> bool:
    d, o, u = get_prices(chat_id)
    return d is not None or bool(o) or bool(u)


def build_sales_report(title, rows, prices, full=False, note=None):
    default, owners, users = prices
    if not rows:
        return [f"{title}\n{SEP}\nهنوز چیزی ثبت نشده."]
    groups = defaultdict(list)
    for owner, account, gb, _ in rows:
        price = None
        if account.lower() in users:
            price = users[account.lower()]
        else:
            per_gb = owners.get(owner.lower(), default)
            if per_gb is not None:
                price = per_gb * gb
        groups[owner].append((account, gb, price))

    def owner_sum(us):
        return sum(p for _, _, p in us if p is not None)

    lines = [title]
    if note:
        lines.append(note)
    lines.append(SEP)
    grand = total_gb = 0.0
    unpriced = 0
    for owner, us in sorted(groups.items(), key=lambda kv: -owner_sum(kv[1])):
        s_owner = owner_sum(us)
        gbs = sum(g for _, g, _ in us)
        miss = sum(1 for _, _, p in us if p is None)
        grand += s_owner
        total_gb += gbs
        unpriced += miss
        lines.append(f"👤 {owner} — {len(us)} کاربر — {fmt_gb(gbs)}")
        lines.append(f"   💵 {money(s_owner)}" + (f"   ⚠️ {miss} بدون قیمت" if miss else ""))
        if full:
            for account, gb, price in sorted(us, key=lambda x: -(x[2] or 0)):
                lines.append(f"   • {account} — {fmt_gb(gb)} — {money(price) if price is not None else 'بدون قیمت'}")
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    lines += [SEP, f"💰 جمع فروش: {money(grand)}", f"📦 {fmt_gb(total_gb)} | 👥 {len(rows)} کاربر"]
    if unpriced:
        lines.append("⚠️ برای کاربرهای بدون قیمت: /price یا /userprice")
    return chunk_text("\n".join(lines))


def sales_chunks(chat_id, scope, title, full=False):
    if not has_prices(chat_id):
        return None
    return build_sales_report(title, get_rows(chat_id, scope), get_prices(chat_id), full)


# ---------- افزودن و حذف دستی ----------
def ensure_chat(chat_id):
    con = db()
    with con:
        con.execute(
            "INSERT OR IGNORE INTO chats (chat_id, thread_id) VALUES (?,?)",
            (chat_id, None if TOPIC_ID == 1 else TOPIC_ID),
        )
    con.close()


def add_manual(chat_id, account, gb, owner):
    ensure_chat(chat_id)
    con = db()
    try:
        with con:
            mid = -int(time.time() * 1000)
            while con.execute("SELECT 1 FROM entries WHERE chat_id=? AND message_id=?", (chat_id, mid)).fetchone():
                mid -= 1
            con.execute(
                "INSERT INTO entries (chat_id, message_id, idx, sender_id, sender_name, owner, gb, account,"
                " week_id, created_at) VALUES (?,?,?,?,?,?,?,?,NULL,?)",
                (chat_id, mid, 0, 0, "manual", owner, gb, account, now_iso()),
            )
    finally:
        con.close()


def find_entries(chat_id, account):
    con = db()
    rows = con.execute(
        "SELECT e.rowid, e.owner, e.account, e.gb, w.number FROM entries e"
        " LEFT JOIN weeks w ON w.id = e.week_id"
        " WHERE e.chat_id=? AND lower(e.account)=lower(?) ORDER BY e.created_at DESC LIMIT 10",
        (chat_id, account),
    ).fetchall()
    con.close()
    return rows


def delete_entry(rowid):
    con = db()
    try:
        with con:
            row = con.execute(
                "SELECT chat_id, owner, account, gb, week_id FROM entries WHERE rowid=?", (rowid,)
            ).fetchone()
            if not row:
                return None
            chat_id, owner, account, gb, week_id = row
            con.execute("DELETE FROM entries WHERE rowid=?", (rowid,))
            if week_id:
                tot, cnt, first = con.execute(
                    "SELECT COALESCE(SUM(gb),0), COUNT(*), MIN(created_at) FROM entries WHERE week_id=?",
                    (week_id,),
                ).fetchone()
                if cnt == 0:
                    con.execute("DELETE FROM weeks WHERE id=?", (week_id,))
                    ids = [
                        r[0]
                        for r in con.execute(
                            "SELECT id FROM weeks WHERE chat_id=? ORDER BY closed_at, id", (chat_id,)
                        )
                    ]
                    for n, wid in enumerate(ids, 1):
                        con.execute("UPDATE weeks SET number=? WHERE id=?", (n, wid))
                else:
                    con.execute(
                        "UPDATE weeks SET total_gb=?, count=?, started_at=? WHERE id=?",
                        (tot, cnt, first, week_id),
                    )
            return {"owner": owner, "account": account, "gb": gb, "closed": bool(week_id)}
    finally:
        con.close()


# ---------- بکاپ و ریستور ----------
def backup_name() -> str:
    return "sum-bot-backup-" + datetime.now(TZ).strftime("%Y%m%d-%H%M") + ".db"


def make_backup_file():
    db().close()
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return path


def inspect_backup(path):
    try:
        con = sqlite3.connect(path)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return {"error": "فایل بکاپ خراب است."}
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "entries" not in tables:
                return {"error": "این فایل، بکاپ این ربات نیست."}

            def count(t):
                return con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if t in tables else 0

            return {
                "entries": count("entries"),
                "weeks": count("weeks"),
                "prices": count("prices") + count("user_prices"),
            }
        finally:
            con.close()
    except sqlite3.Error:
        return {"error": "فایل بکاپ معتبر نیست."}


def do_restore(path):
    safety = None
    if os.path.exists(DB_PATH):
        safety = f"{DB_PATH}.before-restore-{datetime.now(TZ).strftime('%Y%m%d-%H%M%S')}"
        a, b = sqlite3.connect(DB_PATH), sqlite3.connect(safety)
        try:
            a.backup(b)
        finally:
            b.close()
            a.close()
    src, dst = sqlite3.connect(path), sqlite3.connect(DB_PATH)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    os.remove(path)
    db().close()  # مهاجرت ستون‌ها/جدول‌های جدید برای بکاپ‌های قدیمی
    return safety


# ---------- کمکی ----------
def in_topic(msg) -> bool:
    if msg.chat.type == "channel":
        return True
    tid = msg.message_thread_id if msg.is_topic_message else None
    if TOPIC_ID == 1:  # تاپیک General
        return tid in (None, 1)
    return tid == TOPIC_ID


def sender_of(msg):
    if msg.sender_chat:
        return msg.sender_chat.id, msg.sender_chat.title or "کانال"
    u = msg.from_user
    return u.id, u.full_name


def allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    msg = update.effective_message
    if msg is None or (msg.from_user is None and msg.sender_chat is None):
        return False
    if msg.from_user and msg.from_user.id == context.bot.id:
        return False  # پیام‌های خود ربات (جلوگیری از حلقه)
    if CHAT_ID and msg.chat_id != CHAT_ID:
        return False
    return in_topic(msg)


async def is_admin(context, chat_id, user_id, sender_chat_id=None) -> bool:
    if sender_chat_id == chat_id:  # ادمین ناشناس
        return True
    try:
        m = await context.bot.get_chat_member(chat_id, user_id)
        return m.status in ("creator", "administrator")
    except Exception:  # noqa: BLE001
        return False


def command_ok(update: Update) -> bool:
    """اگر OWNER_IDS تنظیم شده باشد فقط همان‌ها؛ بقیه بی‌صدا نادیده گرفته می‌شوند."""
    if not OWNER_IDS:
        return True
    u = update.effective_user
    return bool(u and u.id in OWNER_IDS)


def parse_args(args, default_short):
    short, number = default_short, None
    for a in args or []:
        a = a.lower()
        if a in ("short", "خلاصه"):
            short = True
        elif a in ("full", "کامل"):
            short = False
        elif a.isdigit():
            number = int(a)
    return short, number


async def send_chunks(msg, chunks, reply_markup=None):
    for i, c in enumerate(chunks):
        last = i == len(chunks) - 1
        await msg.reply_text(c, reply_markup=reply_markup if last else None)


# ---------- هندلرها ----------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None:
        return
    if not allowed(update, context):
        if TAG_RE.search(msg.text or ""):
            log.info(
                "پیام #Create_User نادیده گرفته شد (chat=%s topic=%s). در همان تاپیک /status را بزنید.",
                msg.chat_id,
                msg.message_thread_id,
            )
        return
    items = parse_message(msg.text or "")
    if not items:
        return
    remember_chat(msg.chat_id, msg.message_thread_id if msg.is_topic_message else None)
    sender_id, sender_name = sender_of(msg)
    created = msg.date.astimezone(timezone.utc).isoformat()
    if not save_entries(msg.chat_id, msg.message_id, sender_id, sender_name, items, created):
        log.info("پیام %s در هفته‌ی بسته‌شده است؛ ویرایش نادیده گرفته شد", msg.message_id)
        return
    if update.edited_message is not None or update.edited_channel_post is not None:
        return
    if REPLY_EACH:
        gb, owner, account = items[0]
        await msg.reply_text(f"✅ {account} — {fmt_gb(gb)} — از طرف: {owner}")
    elif REACT:
        try:
            await msg.set_reaction(ReactionTypeEmoji("👍"))
        except Exception as e:  # noqa: BLE001
            log.debug("reaction failed: %s", e)


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context) or not command_ok(update):
        return
    msg = update.effective_message
    short, number = parse_args(context.args, default_short=False)
    if number is not None:
        w = get_week(msg.chat_id, number)
        if not w:
            await msg.reply_text(f"هفته‌ی {number} پیدا نشد. با /weeks فهرست را ببینید.")
            return
        rows = get_rows(msg.chat_id, w[0])
        await send_chunks(msg, build_report(closed_title(w[1], w[2], w[3]), rows, short))
        return
    rows = get_rows(msg.chat_id, "open")
    note = None
    if rows:
        note = "⏳ هنوز بسته نشده؛ بستن دستی: /closeweek"
        if AUTO_CLOSE:
            note += f"\n🕒 بستن خودکار: {next_boundary_text()}"
    await send_chunks(msg, build_report(open_title(msg.chat_id, rows), rows, short, note))


async def cmd_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context) or not command_ok(update):
        return
    msg = update.effective_message
    short, _ = parse_args(context.args, default_short=True)
    rows = get_rows(msg.chat_id, "all")
    closed = len(list_weeks(msg.chat_id))
    note = f"هفته‌های بسته‌شده: {closed} | به‌علاوه‌ی هفته‌ی جاری"
    await send_chunks(msg, build_report("📊 جمع کل همه‌ی هفته‌ها", rows, short, note))


async def cmd_weeks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context) or not command_ok(update):
        return
    msg = update.effective_message
    weeks = list_weeks(msg.chat_id)
    open_rows = get_rows(msg.chat_id, "open")
    lines = ["🗂 هفته‌ها", SEP]
    for _, number, started, closed, total, count in weeks:
        lines.append(
            f"هفته {number} | {fmt_date(started)} تا {fmt_date(closed)}\n"
            f"   {fmt_gb(total)} — {count} کاربر"
        )
    if open_rows:
        total = sum(r[2] for r in open_rows)
        lines.append(f"⏳ هفته‌ی جاری | {fmt_gb(total)} — {len(open_rows)} کاربر (بسته نشده)")
    if len(lines) == 2:
        lines.append("هنوز چیزی ثبت نشده.")
    lines.append(SEP)
    lines.append("جزئیات یک هفته: /week شماره")
    await send_chunks(msg, chunk_text("\n".join(lines)))


async def cmd_closeweek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update, context) or not command_ok(update):
        return
    msg = update.effective_message
    sc = msg.sender_chat.id if msg.sender_chat else None
    uid = msg.from_user.id if msg.from_user else 0
    if not OWNER_IDS and not await is_admin(context, msg.chat_id, uid, sc):
        await msg.reply_text("فقط ادمین‌ها می‌توانند هفته را ببندند.")
        return
    rows = get_rows(msg.chat_id, "open")
    if not rows:
        await msg.reply_text("هفته‌ی جاری خالی است؛ چیزی برای بستن نیست.")
        return
    chunks = build_report(open_title(msg.chat_id, rows), rows, short=True)
    chunks[-1] += "\n\nاین هفته بسته شود؟ بعد از بستن، ثبت‌ها از صفر شروع می‌شود."
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ بستن هفته", callback_data="close:yes"),
            InlineKeyboardButton("❌ انصراف", callback_data="close:no"),
        ]]
    )
    await send_chunks(msg, chunks, reply_markup=kb)


async def on_close_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat_id = q.message.chat_id
    if OWNER_IDS:
        ok = q.from_user.id in OWNER_IDS
    else:
        ok = await is_admin(context, chat_id, q.from_user.id)
    if not ok:
        await q.answer("اجازه ندارید", show_alert=True)
        return
    await q.answer()
    if q.data == "close:no":
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text("❌ بستن هفته لغو شد.")
        return
    w = close_week(chat_id)
    await q.edit_message_reply_markup(reply_markup=None)
    if not w:
        await q.message.reply_text("این هفته قبلاً بسته شده یا چیزی ثبت نشده بود.")
        return
    rows = get_rows(chat_id, w["id"])
    chunks = build_report(
        "🔒 " + closed_title(w["number"], w["started"], w["closed"]) + " بسته شد",
        rows,
        short=False,
        note=f"✅ از این به بعد ثبت‌ها برای هفته‌ی {w['number'] + 1} است",
    )
    await send_chunks(q.message, chunks)
    sc = sales_chunks(chat_id, w["id"], f"💰 فروش هفته {w['number']}")
    if sc:
        await send_chunks(q.message, sc)


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not command_ok(update):
        return
    if msg.chat.type == "private":
        chat_id = CHAT_ID or single_known_chat()
    else:
        if not allowed(update, context):
            return
        chat_id = msg.chat_id
    args = [a.lower() for a in (context.args or [])]
    chunks = None if ("help" in args or "import" in args or not chat_id) else build_analysis(chat_id)
    if not chunks:
        await msg.reply_text(HOWTO_IMPORT)
        return
    await send_chunks(msg, chunks)


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or msg.document is None or msg.chat.type != "private" or msg.from_user is None:
        return
    uid = msg.from_user.id
    if not OWNER_IDS:
        await msg.reply_text(
            "برای ایمپورت اول باید آیدی خودتان را در OWNER_IDS بگذارید.\n"
            f"آیدی شما: {uid}\n"
            "روی سرور: nano /opt/sum-bot/.env ← OWNER_IDS=آیدی ← systemctl restart sum-bot"
        )
        return
    if uid not in OWNER_IDS:
        return
    doc = msg.document
    fname = (doc.file_name or "").lower()
    if fname.endswith(".db") or fname.endswith(".sqlite"):
        await handle_restore_file(msg, doc)
        return
    if not fname.endswith(".json"):
        await msg.reply_text(
            "فایل باید result.json (برای ایمپورت پیام‌های قدیمی) یا فایل بکاپ .db (برای ریستور) باشد.\n"
            "راهنما: /analyze help"
        )
        return
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await msg.reply_text("فایل بزرگ‌تر از ۲۰ مگابایت است. هنگام Export رسانه‌ها را خاموش کنید یا بازه‌ی زمانی را کوتاه کنید.")
        return
    await msg.reply_text("⏳ در حال خواندن فایل...")
    try:
        tg_file = await doc.get_file()
        data = await tg_file.download_as_bytearray()
        obj = json.loads(bytes(data).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("import read failed: %s", e)
        await msg.reply_text("خواندن فایل ناموفق بود. مطمئن شوید JSON است و کامل آپلود شده.")
        return
    res = await asyncio.to_thread(import_history, obj)
    if "error" in res:
        await msg.reply_text(res["error"])
        return
    await msg.reply_text(
        "✅ ایمپورت انجام شد\n"
        f"• پیام‌های #Create_User پیداشده: {res['found']}\n"
        f"• کاربرهای تازه ثبت‌شده: {res['added']} (تکراری/ردشده: {res['skipped']})\n"
        f"• هفته‌های ساخته یا به‌روزشده: {res['weeks']}\n"
        f"• ثبت‌های هفته‌ی جاری (هنوز باز): {res['open_added']}\n"
        "شماره‌ی هفته‌ها بر اساس تاریخ دوباره مرتب شد."
    )
    chunks = build_analysis(res["chat_id"])
    if chunks:
        await send_chunks(msg, chunks)


async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not command_ok(update):
        return
    if msg.chat.type != "private" and not allowed(update, context):
        return
    await msg.reply_text(f"🤖 نسخه‌ی ربات: {local_version()}")


async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None:
        return
    if not OWNER_IDS:
        await msg.reply_text(
            "برای آپدیت از داخل ربات باید OWNER_IDS در .env تنظیم شده باشد.\n"
            "یا روی سرور بزنید: sum-bot update"
        )
        return
    if not owner_only(update):
        return
    force = "force" in [a.lower() for a in (context.args or [])]
    cur = local_version()
    latest = await asyncio.to_thread(fetch_latest_version)
    if latest is None:
        await msg.reply_text("❌ اتصال به GitHub ناموفق بود. بعداً دوباره امتحان کنید.")
        return
    if vtuple(latest) <= vtuple(cur) and not force:
        await msg.reply_text(
            f"✅ ربات آپدیت است (نسخه‌ی {cur}).\n"
            "اگر کد را بدون تغییر شماره‌ی نسخه عوض کرده‌اید: /update force"
        )
        return
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("⬆️ آپدیت", callback_data="upd:yes"),
            InlineKeyboardButton("❌ انصراف", callback_data="upd:no"),
        ]]
    )
    await msg.reply_text(
        f"🆕 نسخه‌ی روی GitHub: {latest}\nنسخه‌ی فعلی: {cur}\n\n"
        "آپدیت شود؟ ربات چند ثانیه ریستارت می‌شود.",
        reply_markup=kb,
    )


async def on_update_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not owner_only(update):
        await q.answer("اجازه ندارید", show_alert=True)
        return
    await q.answer()
    await q.edit_message_reply_markup(reply_markup=None)
    if q.data == "upd:no":
        await q.message.reply_text("❌ آپدیت لغو شد.")
        return
    await q.message.reply_text("⏳ در حال آپدیت...")
    ok, out = await asyncio.to_thread(run_update)
    if not ok:
        await q.message.reply_text("❌ آپدیت ناموفق بود:\n" + out[-800:])
        return
    await q.message.reply_text(
        f"✅ کد به نسخه‌ی {local_version()} آپدیت شد. ربات در حال ریستارت است؛ چند ثانیه صبر کنید."
    )
    subprocess.Popen(["systemctl", "restart", SERVICE_NAME], start_new_session=True)


async def update_check_loop(app):
    await asyncio.sleep(60)
    while True:
        try:
            latest = await asyncio.to_thread(fetch_latest_version)
            if latest and vtuple(latest) > vtuple(local_version()) and get_state("notified_version") != latest:
                sent = False
                for uid in OWNER_IDS:
                    try:
                        await app.bot.send_message(
                            uid,
                            f"🆕 نسخه‌ی جدید ربات: {latest} (فعلی: {local_version()})\n"
                            "برای آپدیت /update را بفرستید.",
                        )
                        sent = True
                    except Exception as e:  # noqa: BLE001
                        log.debug("update notice failed: %s", e)
                if sent:
                    set_state("notified_version", latest)
        except Exception:  # noqa: BLE001
            log.exception("update check failed")
        await asyncio.sleep(12 * 3600)


HELP_TEXT = (
    "📖 دستورها\n\n"
    "گزارش:\n"
    "/week [شماره] — هفته‌ی جاری یا یک هفته‌ی بسته‌شده\n"
    "/total — جمع کل | /weeks — فهرست هفته‌ها | /analyze — تحلیل کامل\n"
    "/closeweek — بستن دستی هفته\n\n"
    "حساب و کتاب:\n"
    "/price — نمایش قیمت‌ها | /price MSN 1500 — قیمت هر گیگ برای یک Belongs To\n"
    "/price all 1000 — قیمت پیش‌فرض | /userprice Ali 90000 — قیمت ثابت یک کاربر\n"
    "/sales [شماره|total] [full] — فروش به تومان\n\n"
    "ویرایش داده:\n"
    "/add Ali 30 MSN — افزودن دستی | /remove Ali — حذف\n\n"
    "بکاپ و نگهداری:\n"
    "/backup — فایل بکاپ (در پیوی) | فایل .db را در پیوی بفرستید تا ریستور شود\n"
    "/status — عیب‌یابی | /version | /update"
)

SEEN = {"others": 0, "last_tag": None}


async def pre_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قبل از بقیه اجرا می‌شود: آمار عیب‌یابی + حذف پیام‌های ناخواسته‌ی ربات‌های دیگر."""
    msg = update.effective_message
    if msg is None or msg.chat.type == "private":
        return
    text = msg.text or ""
    u = msg.from_user
    from_other = bool((u and u.is_bot and u.id != context.bot.id) or msg.chat.type == "channel")
    if not from_other:
        return
    SEEN["others"] += 1
    if TAG_RE.search(text):
        SEEN["last_tag"] = {
            "chat": msg.chat_id,
            "type": msg.chat.type,
            "thread": msg.message_thread_id if msg.is_topic_message else None,
            "time": time.time(),
        }
    if should_delete(text) and (not CHAT_ID or msg.chat_id == CHAT_ID):
        try:
            await msg.delete()
        except Exception as e:  # noqa: BLE001
            log.warning("حذف پیام ناموفق (ربات باید ادمین با دسترسی Delete messages باشد): %s", e)


async def need_owner(update: Update) -> bool:
    msg = update.effective_message
    if msg is None:
        return False
    if not OWNER_IDS:
        await msg.reply_text(
            "این دستور فقط برای مالک است. اول OWNER_IDS را در .env بگذارید (آیدی شما با /myid)، "
            "بعد: sum-bot restart"
        )
        return False
    return owner_only(update)


async def get_chat_or_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None:
        return None
    if msg.chat.type == "private":
        cid = CHAT_ID or single_known_chat()
        if not cid:
            await msg.reply_text("هنوز گروهی ثبت نشده. CHAT_ID را در .env بگذارید یا اول یک پیام در گروه ثبت شود.")
        return cid
    return msg.chat_id if allowed(update, context) else None


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not command_ok(update):
        return
    await msg.reply_text(HELP_TEXT)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not command_ok(update):
        return
    here_thread = msg.message_thread_id if msg.is_topic_message else None
    lines = [
        f"🩺 وضعیت ربات — نسخه {local_version()}",
        SEP,
        f"• این چت: {msg.chat_id} | این تاپیک: {here_thread or 'General / بدون تاپیک'}",
        f"• تنظیم‌شده: CHAT_ID={CHAT_ID or 'خالی'} | TOPIC_ID={TOPIC_ID}",
    ]
    try:
        me = await context.bot.get_me()
        priv = getattr(me, "can_read_all_group_messages", None)
        if priv is not None:
            lines.append("• Privacy خاموش است: " + ("بله ✅" if priv else "خیر ❌ (در BotFather: /setprivacy ← Disable)"))
    except Exception:  # noqa: BLE001
        pass
    if msg.chat.type in ("group", "supergroup", "channel"):
        try:
            m = await context.bot.get_chat_member(msg.chat_id, context.bot.id)
            is_adm = m.status in ("administrator", "creator")
            can_del = m.status == "creator" or bool(getattr(m, "can_delete_messages", False))
            lines.append("• ربات ادمین است: " + ("بله ✅" if is_adm else "خیر ❌"))
            lines.append("• دسترسی حذف پیام: " + ("بله ✅" if can_del else "خیر ❌ (برای حذف «User not found»)"))
        except Exception:  # noqa: BLE001
            pass
    lines.append(f"• پیام‌های ربات‌ها/کانال‌ها که از آخرین ریستارت دیده‌ام: {SEEN['others']}")
    lt = SEEN["last_tag"]
    if lt:
        mins = int((time.time() - lt["time"]) / 60)
        if CHAT_ID and lt["chat"] != CHAT_ID:
            verdict = f"❌ نادیده گرفته می‌شود: CHAT_ID فرق دارد (چت واقعی: {lt['chat']})"
        elif lt["type"] != "channel" and not (
            (lt["thread"] in (None, 1)) if TOPIC_ID == 1 else (lt["thread"] == TOPIC_ID)
        ):
            verdict = f"❌ نادیده گرفته می‌شود: تاپیک فرق دارد (تاپیک واقعی: {lt['thread']}، TOPIC_ID را همین بگذارید)"
        else:
            verdict = "✅ شمرده می‌شود"
        lines.append(f"• آخرین #Create_User: {mins} دقیقه پیش — چت {lt['chat']} — تاپیک {lt['thread']} — {verdict}")
    else:
        lines.append(
            "• از آخرین ریستارت هیچ پیام #Create_User ندیده‌ام. اگر پاسارگارد پیام فرستاده، یعنی "
            "Bot-to-Bot Mode خاموش است یا ربات ادمین/Privacy درست نیست یا پیام در چت دیگری می‌آید."
        )
    con = db()
    n = con.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    con.close()
    lines.append(f"• ثبت‌شده در دیتابیس: {n} کاربر")
    await msg.reply_text("\n".join(lines))


async def cmd_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not command_ok(update):
        return
    chat_id = await get_chat_or_reply(update, context)
    if not chat_id:
        return
    args = [a.lower() for a in (context.args or [])]
    full = "full" in args or "کامل" in args
    prices = get_prices(chat_id)
    if prices[0] is None and not prices[1] and not prices[2]:
        await msg.reply_text("هنوز قیمتی تعیین نشده. مثال:\n/price MSN 1500\n/price all 1000")
        return
    number = next((int(a) for a in args if a.isdigit()), None)
    if "total" in args or "کل" in args:
        rows, title = get_rows(chat_id, "all"), "💰 فروش کل همه‌ی هفته‌ها"
    elif number is not None:
        w = get_week(chat_id, number)
        if not w:
            await msg.reply_text(f"هفته‌ی {number} پیدا نشد. با /weeks فهرست را ببینید.")
            return
        rows, title = get_rows(chat_id, w[0]), "💰 فروش " + closed_title(w[1], w[2], w[3])
    else:
        rows = get_rows(chat_id, "open")
        title = "💰 فروش هفته‌ی جاری"
    await send_chunks(msg, build_sales_report(title, rows, prices, full))


async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not command_ok(update):
        return
    chat_id = await get_chat_or_reply(update, context)
    if not chat_id:
        return
    args = context.args or []
    if not args:
        default, _, _ = get_prices(chat_id)
        owners, users = list_prices(chat_id)
        lines = [
            "💵 قیمت‌ها (به ازای هر گیگ)",
            SEP,
            f"پیش‌فرض: {money(default) if default is not None else 'تعیین نشده'}",
        ]
        lines += [f"• {o}: {money(p)}" for o, p in owners]
        if users:
            lines += ["", "قیمت ثابت کاربرها:"] + [f"• {a}: {money(p)}" for a, p in users[:30]]
        lines += [
            SEP,
            "تنظیم: /price MSN 1500   |   /price all 1000   |   /userprice Ali 90000",
            "حذف: /price MSN off   |   /userprice Ali off",
        ]
        await send_chunks(msg, chunk_text("\n".join(lines)))
        return
    if not await need_owner(update):
        return
    if len(args) < 2:
        await msg.reply_text("مثال: /price MSN 1500   یا   /price all 1000")
        return
    value_txt, owner = args[-1], " ".join(args[:-1])
    if value_txt.lower() in ("off", "حذف", "delete"):
        value = None
    else:
        value = parse_number(value_txt)
        if value is None or value < 0:
            await msg.reply_text("قیمت باید عدد باشد. مثال: /price MSN 1500")
            return
    key = "*" if owner.lower() in ("all", "*", "default", "همه", "پیش‌فرض") else owner
    set_owner_price(chat_id, key, value)
    who = "پیش‌فرض" if key == "*" else key
    await msg.reply_text(
        f"✅ قیمت {who} حذف شد." if value is None else f"✅ قیمت {who}: {money(value)} به ازای هر گیگ"
    )


async def cmd_userprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not command_ok(update):
        return
    chat_id = await get_chat_or_reply(update, context)
    if not chat_id or not await need_owner(update):
        return
    args = context.args or []
    if len(args) != 2:
        await msg.reply_text(
            "مثال: /userprice Ali 90000   (قیمت کل همان کاربر، مستقل از حجم)\nحذف: /userprice Ali off"
        )
        return
    account, value_txt = args
    if value_txt.lower() in ("off", "حذف", "delete"):
        set_user_price(chat_id, account, None)
        await msg.reply_text(f"✅ قیمت ثابت {account} حذف شد (دوباره با قیمت هر گیگ محاسبه می‌شود).")
        return
    value = parse_number(value_txt)
    if value is None or value < 0:
        await msg.reply_text("قیمت باید عدد باشد. مثال: /userprice Ali 90000")
        return
    set_user_price(chat_id, account, value)
    await msg.reply_text(f"✅ قیمت {account}: {money(value)} (برای هر ثبتِ این نام‌کاربری)")


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not command_ok(update):
        return
    chat_id = await get_chat_or_reply(update, context)
    if not chat_id or not await need_owner(update):
        return
    usage = "مثال: /add Ali 30 MSN\n(نام‌کاربری، حجم، Belongs To). با واحد: /add Ali 500MB MSN"
    args = context.args or []
    if len(args) < 3:
        await msg.reply_text(usage)
        return
    account, rest = args[0], args[1:]
    if len(rest) >= 3 and rest[1].lower() in ("mb", "gb", "tb"):
        size_txt, owner = rest[0] + rest[1], " ".join(rest[2:])
    else:
        size_txt, owner = rest[0], " ".join(rest[1:])
    gb = parse_size(size_txt)
    if gb is None or gb <= 0 or not owner.strip():
        await msg.reply_text(usage)
        return
    await asyncio.to_thread(add_manual, chat_id, account, gb, owner.strip())
    total = sum(r[2] for r in get_rows(chat_id, "open"))
    await msg.reply_text(
        f"➕ اضافه شد (هفته‌ی جاری): {account} — {fmt_gb(gb)} — {owner.strip()}\n"
        f"📊 جمع هفته‌ی جاری: {fmt_gb(total)}"
    )


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not command_ok(update):
        return
    chat_id = await get_chat_or_reply(update, context)
    if not chat_id or not await need_owner(update):
        return
    if not context.args:
        await msg.reply_text("مثال: /remove Ali   (نام‌کاربری را بدهید، ثبت‌های او را نشان می‌دهم)")
        return
    account = context.args[0]
    rows = await asyncio.to_thread(find_entries, chat_id, account)
    if not rows:
        await msg.reply_text(f"ثبتی با نام «{account}» پیدا نشد.")
        return
    buttons = []
    for rowid, owner, acc, gb, wnum in rows:
        label = f"هفته {wnum}" if wnum else "هفته‌ی جاری"
        buttons.append(
            [InlineKeyboardButton(f"🗑 {acc} — {fmt_gb(gb)} — {owner} — {label}", callback_data=f"del:{rowid}")]
        )
    buttons.append([InlineKeyboardButton("❌ انصراف", callback_data="del:no")])
    await msg.reply_text("کدام ثبت حذف شود؟", reply_markup=InlineKeyboardMarkup(buttons))


async def on_delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not owner_only(update):
        await q.answer("اجازه ندارید", show_alert=True)
        return
    await q.answer()
    await q.edit_message_reply_markup(reply_markup=None)
    if q.data == "del:no":
        await q.message.reply_text("❌ لغو شد.")
        return
    r = await asyncio.to_thread(delete_entry, int(q.data.split(":")[1]))
    if not r:
        await q.message.reply_text("این ثبت قبلاً حذف شده بود.")
        return
    extra = " (از یک هفته‌ی بسته‌شده؛ جمع آن هفته به‌روز شد)" if r["closed"] else ""
    await q.message.reply_text(f"🗑 حذف شد: {r['account']} — {fmt_gb(r['gb'])} — {r['owner']}{extra}")


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg is None or not await need_owner(update):
        return
    if msg.chat.type != "private":
        await msg.reply_text("🔒 برای امنیت، بکاپ فقط در پیوی ربات فرستاده می‌شود. همین دستور را در پیوی ربات بزنید.")
        return
    path = await asyncio.to_thread(make_backup_file)
    try:
        with open(path, "rb") as f:
            await msg.reply_document(
                f,
                filename=backup_name(),
                caption="📦 بکاپ دیتابیس. برای ریستور همین فایل را در پیوی ربات بفرستید.",
            )
    finally:
        os.remove(path)


async def send_backup_to_owners(bot, caption):
    path = await asyncio.to_thread(make_backup_file)
    try:
        for uid in OWNER_IDS:
            try:
                with open(path, "rb") as f:
                    await bot.send_document(uid, f, filename=backup_name(), caption=caption)
            except Exception as e:  # noqa: BLE001
                log.debug("backup send failed: %s", e)
    finally:
        os.remove(path)


async def handle_restore_file(msg, doc):
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await msg.reply_text("فایل بکاپ بزرگ‌تر از ۲۰ مگابایت است.")
        return
    tg_file = await doc.get_file()
    await tg_file.download_to_drive(RESTORE_TMP)
    info = await asyncio.to_thread(inspect_backup, RESTORE_TMP)
    if "error" in info:
        os.remove(RESTORE_TMP)
        await msg.reply_text("❌ " + info["error"])
        return
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ ریستور", callback_data="rst:yes"),
            InlineKeyboardButton("❌ انصراف", callback_data="rst:no"),
        ]]
    )
    await msg.reply_text(
        "📦 فایل بکاپ پیدا شد:\n"
        f"• ثبت‌ها: {info['entries']}\n• هفته‌ها: {info['weeks']}\n• قیمت‌ها: {info['prices']}\n\n"
        "⚠️ با ریستور، داده‌های فعلی با این فایل جایگزین می‌شوند "
        "(قبلش یک نسخه‌ی ایمن از داده‌ی فعلی کنار دیتابیس ذخیره می‌شود). ادامه؟",
        reply_markup=kb,
    )


async def on_restore_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not owner_only(update):
        await q.answer("اجازه ندارید", show_alert=True)
        return
    await q.answer()
    await q.edit_message_reply_markup(reply_markup=None)
    if q.data == "rst:no":
        if os.path.exists(RESTORE_TMP):
            os.remove(RESTORE_TMP)
        await q.message.reply_text("❌ ریستور لغو شد.")
        return
    if not os.path.exists(RESTORE_TMP):
        await q.message.reply_text("فایل بکاپ پیدا نشد؛ دوباره بفرستید.")
        return
    try:
        safety = await asyncio.to_thread(do_restore, RESTORE_TMP)
    except Exception as e:  # noqa: BLE001
        log.exception("restore failed")
        await q.message.reply_text(f"❌ ریستور ناموفق بود: {e}")
        return
    await q.message.reply_text(
        "✅ ریستور انجام شد."
        + (f"\nنسخه‌ی قبلی داده‌ها اینجا ذخیره شد:\n{safety}" if safety else "")
    )


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u and update.effective_message:
        await update.effective_message.reply_text(f"آیدی عددی شما: {u.id}")


async def auto_close_tick(app, now=None):
    now = now or datetime.now(TZ)
    boundary = last_boundary(now).astimezone(timezone.utc).isoformat()
    last = get_state("last_boundary")
    if last is None:  # اولین اجرا: فقط شروع می‌کنیم، چیزی بسته نمی‌شود
        set_state("last_boundary", boundary)
        return
    if boundary <= last:
        return
    con = db()
    chats = con.execute("SELECT chat_id, thread_id FROM chats").fetchall()
    con.close()
    closed_any = False
    for chat_id, thread_id in chats:
        w = close_week(chat_id, until=boundary)
        if not w:
            continue
        rows = get_rows(chat_id, w["id"])
        chunks = build_report(
            "🔒 " + closed_title(w["number"], w["started"], w["closed"]) + " خودکار بسته شد",
            rows,
            short=False,
            note=f"✅ از این به بعد ثبت‌ها برای هفته‌ی {w['number'] + 1} است",
        )
        for c in chunks:
            try:
                await app.bot.send_message(chat_id, c, message_thread_id=thread_id)
            except Exception as e:  # noqa: BLE001
                log.warning("ارسال گزارش خودکار ناموفق: %s", e)
        sc = sales_chunks(chat_id, w["id"], f"💰 فروش هفته {w['number']}")
        for c in sc or []:
            try:
                await app.bot.send_message(chat_id, c, message_thread_id=thread_id)
            except Exception as e:  # noqa: BLE001
                log.warning("ارسال گزارش فروش ناموفق: %s", e)
        closed_any = True
    set_state("last_boundary", boundary)
    if closed_any and AUTO_BACKUP and OWNER_IDS:
        await send_backup_to_owners(app.bot, "📦 بکاپ خودکار بعد از بستن هفته")


async def auto_loop(app):
    await asyncio.sleep(5)
    while True:
        try:
            await auto_close_tick(app)
        except Exception:  # noqa: BLE001
            log.exception("auto close failed")
        await asyncio.sleep(60)


async def post_init(app: Application):
    if AUTO_CLOSE:
        app.bot_data["auto_task"] = asyncio.create_task(auto_loop(app))
    if UPDATE_CHECK and OWNER_IDS:
        app.bot_data["upd_task"] = asyncio.create_task(update_check_loop(app))
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("week", "گزارش هفته‌ی جاری"),
                BotCommand("closeweek", "بستن هفته (ادمین)"),
                BotCommand("total", "جمع کل"),
                BotCommand("weeks", "فهرست هفته‌ها"),
                BotCommand("analyze", "تحلیل کامل"),
                BotCommand("version", "نسخه‌ی ربات"),
                BotCommand("update", "آپدیت ربات (مالک)"),
                BotCommand("sales", "فروش به تومان"),
                BotCommand("price", "قیمت‌ها"),
                BotCommand("add", "افزودن دستی"),
                BotCommand("remove", "حذف ثبت"),
                BotCommand("backup", "بکاپ (پیوی)"),
                BotCommand("status", "عیب‌یابی"),
                BotCommand("help", "راهنما"),
            ]
        )
    except Exception as e:  # noqa: BLE001
        log.warning("set_my_commands failed: %s", e)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN تنظیم نشده است.")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("closeweek", cmd_closeweek))
    app.add_handler(CommandHandler("total", cmd_total))
    app.add_handler(CommandHandler("weeks", cmd_weeks))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("version", cmd_version))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(CallbackQueryHandler(on_update_button, pattern=r"^upd:"))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, on_document))
    app.add_handler(CallbackQueryHandler(on_close_button, pattern=r"^close:"))
    for name, fn in (
        ("help", cmd_help),
        ("status", cmd_status),
        ("sales", cmd_sales),
        ("price", cmd_price),
        ("userprice", cmd_userprice),
        ("add", cmd_add),
        ("remove", cmd_remove),
        ("backup", cmd_backup),
    ):
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_delete_button, pattern=r"^del:"))
    app.add_handler(CallbackQueryHandler(on_restore_button, pattern=r"^rst:"))
    app.add_handler(MessageHandler(filters.TEXT, pre_handler), group=-1)
    app.add_handler(
        MessageHandler(
            (filters.ChatType.GROUPS | filters.ChatType.CHANNEL) & filters.TEXT & ~filters.COMMAND, on_text
        )
    )
    app.run_polling()


if __name__ == "__main__":
    main()

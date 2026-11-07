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
    /myid            آیدی عددی خودتان (برای تنظیم OWNER_IDS)
    به همه‌ی گزارش‌ها می‌توانید short (خلاصه) یا full (کامل) اضافه کنید

نصب:   pip install "python-telegram-bot>=21"
اجرا:  BOT_TOKEN=... TOPIC_ID=1 OWNER_IDS=123456789 python3 sum_bot.py

نکته: تلگرام پیام ربات‌ها را به ربات‌های دیگر نمی‌دهد. در @BotFather برای هر دو
ربات (پاسارگارد و این ربات) Bot-to-Bot Communication Mode را روشن کنید،
این ربات را ادمین گروه کنید و Group Privacy را Disable کنید.
"""

import asyncio
import logging
import os
import re
import sqlite3
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
COUNT_TAGS = {
    t.strip().lower()
    for t in os.getenv("COUNT_TAGS", "#Create_User").split(",")
    if t.strip()
}

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


# ---------- کمکی ----------
def in_topic(msg) -> bool:
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
    if not allowed(update, context):
        return
    msg = update.effective_message
    items = parse_message(msg.text or "")
    if not items:
        return
    remember_chat(msg.chat_id, msg.message_thread_id if msg.is_topic_message else None)
    sender_id, sender_name = sender_of(msg)
    created = msg.date.astimezone(timezone.utc).isoformat()
    if not save_entries(msg.chat_id, msg.message_id, sender_id, sender_name, items, created):
        log.info("پیام %s در هفته‌ی بسته‌شده است؛ ویرایش نادیده گرفته شد", msg.message_id)
        return
    if update.edited_message is not None:
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
    set_state("last_boundary", boundary)


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
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("week", "گزارش هفته‌ی جاری"),
                BotCommand("closeweek", "بستن هفته (ادمین)"),
                BotCommand("total", "جمع کل"),
                BotCommand("weeks", "فهرست هفته‌ها"),
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
    app.add_handler(CallbackQueryHandler(on_close_button, pattern=r"^close:"))
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, on_text)
    )
    app.run_polling()


if __name__ == "__main__":
    main()

# Sum Bot

ربات تلگرام برای جمع زدن حجم کاربران ساخته‌شده توسط پنل پاسارگارد (پیام‌های `#Create_User`)،
به تفکیک `Belongs To`، با گزارش هفتگی و جمع کل. هفته‌ی ایرانی (پایان: جمعه ۲۳:۵۹) خودکار بسته می‌شود.

## نصب روی سرور

```bash
REPO_URL=https://github.com/USERNAME/sum-bot.git \
bash <(curl -fsSL https://raw.githubusercontent.com/USERNAME/sum-bot/main/install.sh)
```

آپدیت: همان دستور را دوباره اجرا کنید (تنظیمات و دیتابیس می‌ماند).

## دستورها

| دستور | کار |
|---|---|
| `/week` | گزارش هفته‌ی جاری |
| `/week 3` | گزارش هفته‌ی شماره ۳ |
| `/closeweek` | بستن دستی هفته |
| `/total` | جمع کل |
| `/weeks` | فهرست هفته‌ها |
| `/myid` | آیدی عددی شما |

به گزارش‌ها می‌توان `short` یا `full` اضافه کرد.

## تنظیمات (`/opt/sum-bot/.env`)

`BOT_TOKEN`، `CHAT_ID`، `TOPIC_ID`، `OWNER_IDS`، و اختیاری:
`WEEK_END_DAY` (پیش‌فرض fri)، `WEEK_END_TIME` (پیش‌فرض 23:59)، `AUTO_CLOSE` (0 برای خاموش)،
`REPLY_EACH`، `REACT`، `COUNT_TAGS`.

## نکته‌ی تلگرام

برای دیدن پیام ربات پاسارگارد: Bot-to-Bot Communication Mode را در @BotFather برای هر دو ربات
روشن کنید، ربات را ادمین گروه کنید و Group Privacy را Disable کنید.

> ⚠️ فایل `.env` و توکن را هرگز روی GitHub نگذارید.

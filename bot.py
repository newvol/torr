import asyncio
import json
import logging
import os
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
TZ = ZoneInfo("Europe/Kyiv")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
STATE_PATH = Path(os.getenv("STATE_FILE", "/data/state.json"))
CHECK_SECONDS = max(60, int(os.getenv("CHECK_EVERY_SECONDS", "300")))
SCHEDULE_URL = "https://energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/hrafik-vidkliuchen/"
OUTAGES_URL = "https://energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/chomu-nemaie-elektropostachannia/"
QUEUE_WIDGET_URL = "https://voe-poweron.inneti.net/schedule_queues"
QUEUES = [{"name": "Литовеж", "queue": "4.2"}, {"name": "Нововолинськ", "queue": "2.2"}]
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# Never log HTTP request URLs for Telegram: they contain the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("volyn-bot")


def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"chats": [], "fingerprints": {}, "last_daily": ""}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def safe_url(url):
    parts = urlsplit(url)
    # Drop query and fragment to avoid logging keys/tokens from third-party URLs.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    chat_id = update.effective_chat.id
    if chat_id not in state["chats"]:
        state["chats"].append(chat_id)
        save_state(state)
    await update.message.reply_text(
        "Монітор Волиньобленерго активний.\n"
        "Литовеж — черга 4.2; Нововолинськ — черга 2.2.\n"
        "Команди: /status, /today, /tomorrow."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    last = state.get("last_check", "ще не перевірявся")
    msg = f"Остання перевірка джерела: {last}\nІнтервал: {CHECK_SECONDS // 60} хв.\n"
    msg += "Зчитування годин графіка: ще не підтверджене."
    for p in state.get("source_pages", []):
        msg += f"\n{p.get('title', '')}: {p.get('chars', 0)} символів"
    if state.get("last_error"):
        msg += f"\nПомилка: {state['last_error'][:200]}"
    msg += f"\nОфіційний графік: {SCHEDULE_URL}"
    await update.message.reply_text(msg, disable_web_page_preview=True)


async def read_page(browser, url):
    page = await browser.new_page()
    network = []
    async def on_response(response):
        try:
            parts = urlsplit(response.url)
            content_type = response.headers.get("content-type", "")
            item = {
                "url": safe_url(response.url),
                "status": response.status,
                "type": content_type[:100],
            }
            if ("json" in content_type.lower() or "text/" in content_type.lower()) and len(network) < 35:
                try:
                    body = await response.text()
                    if body:
                        item["sample"] = norm(body)[:350]
                except Exception:
                    pass
            if len(network) < 50:
                network.append(item)
        except Exception:
            pass
    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeoutError:
            pass
        await page.wait_for_timeout(3500)
        text = norm(await page.locator("body").inner_text(timeout=10000))
        frames = []
        for frame in page.frames:
            frames.append({"url": safe_url(frame.url), "name": frame.name})
        iframe_srcs = await page.locator("iframe").evaluate_all(
            "(els) => els.map(e => e.src).filter(Boolean).map(u => { const x = new URL(u); return x.origin + x.pathname; })"
        )
        return {
            "url": safe_url(page.url),
            "title": await page.title(),
            "text": text,
            "frames": frames[:20],
            "iframe_srcs": iframe_srcs[:20],
            "network": network[:35],
        }
    finally:
        await page.close()


def queue_context(text, queue):
    hits = []
    pos = 0
    while True:
        pos = text.find(queue, pos)
        if pos < 0:
            break
        hits.append(text[max(0, pos - 180): min(len(text), pos + 450)])
        pos += len(queue)
    return sorted(set(hits))


async def poll(context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                pages = []
                for url in (SCHEDULE_URL, QUEUE_WIDGET_URL, OUTAGES_URL):
                    try:
                        pages.append(await read_page(browser, url))
                    except Exception as exc:
                        log.warning("Could not read source %s: %s", safe_url(url), str(exc)[:180])
                if not pages:
                    raise RuntimeError("Не вдалося прочитати жодне офіційне джерело")
                state["last_check"] = datetime.now(TZ).isoformat(timespec="seconds")
                state["source_pages"] = [
                    {
                        "url": p["url"], "title": p["title"], "chars": len(p["text"]),
                        "frames": p["frames"], "iframe_srcs": p["iframe_srcs"],
                        "network": p["network"],
                    }
                    for p in pages
                ]
                state["last_error"] = ""
                # Safe diagnostics: response URLs have query strings stripped.
                for p in pages:
                    log.info("Source diagnostic: %s", json.dumps({
                        "url": p["url"], "title": p["title"], "chars": len(p["text"]),
                        "frames": p["frames"], "iframe_srcs": p["iframe_srcs"],
                        "network": p["network"][:20],
                    }, ensure_ascii=False)[:6000])
                widget = next((x for x in pages if "schedule_queues" in x["url"]), None)
                if widget:
                    state["queue_candidates"] = {
                        q["queue"]: queue_context(widget["text"], q["queue"])[:4] for q in QUEUES
                    }
                save_state(state)
            finally:
                await browser.close()
    except Exception as exc:
        state["last_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        save_state(state)
        log.exception("Schedule check failed")


async def daily(context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    today = datetime.now(TZ).date().isoformat()
    if state.get("last_daily") == today:
        return
    tomorrow = (datetime.now(TZ).date() + timedelta(days=1)).strftime("%d.%m.%Y")
    message = (
        f"📅 Графік на завтра — {tomorrow}\n"
        "Литовеж — черга 4.2; Нововолинськ — черга 2.2.\n"
        "Години поки не підтверджені автоматичним зчитуванням. Перевірте офіційний графік: "
        + SCHEDULE_URL
    )
    for chat_id in state.get("chats", []):
        try:
            await context.bot.send_message(chat_id=chat_id, text=message, disable_web_page_preview=True)
        except Exception:
            log.exception("Could not send daily notice to chat %s", chat_id)
    state["last_daily"] = today
    save_state(state)


async def send_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Години черг 4.2 і 2.2 ще не підтверджені парсером. Офіційний графік: " + SCHEDULE_URL,
        disable_web_page_preview=True,
    )


async def send_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Години на завтра ще не підтверджені парсером. Черги: Литовеж 4.2, Нововолинськ 2.2. "
        + SCHEDULE_URL,
        disable_web_page_preview=True,
    )


def main():
    if not TOKEN:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in Railway Variables.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("today", send_today))
    app.add_handler(CommandHandler("tomorrow", send_tomorrow))
    app.job_queue.run_repeating(poll, interval=CHECK_SECONDS, first=5)
    app.job_queue.run_daily(daily, time=time(hour=23, minute=0, tzinfo=TZ), name="tomorrow-schedule")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

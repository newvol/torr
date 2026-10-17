import os
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TZ = ZoneInfo('Europe/Kyiv')
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
SCHEDULE_URL = 'https://energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/hrafik-vidkliuchen/'
OUTAGES_URL = 'https://www.energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/chomu-nemaie-elektropostachannia/'
logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Бот моніторингу Волиньобленерго. Черги: Литовеж 4.2, Нововолинськ 2.2. Напишіть /status для стану.')
    context.application.bot_data.setdefault('chats', set()).add(update.effective_chat.id)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f'Джерело графіка: {SCHEDULE_URL}\nОголошення про перерви: {OUTAGES_URL}\nОфіційний графік оновлюється приблизно щогодини; автоматичний розбір черг ще потребує перевірки.')

async def poll(context: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            a = await client.get(SCHEDULE_URL, headers={'User-Agent':'Mozilla/5.0'})
            b = await client.get(OUTAGES_URL, headers={'User-Agent':'Mozilla/5.0'})
            a.raise_for_status(); b.raise_for_status()
        # Until the queue data parser is verified, only check availability; do not issue false schedule alerts.
        context.application.bot_data['last_check'] = datetime.now(TZ).isoformat()
        context.application.bot_data['source_ok'] = True
    except Exception as exc:
        context.application.bot_data['source_ok'] = False
        logging.exception('Source check failed: %s', exc)

async def tomorrow(context: ContextTypes.DEFAULT_TYPE):
    day = (datetime.now(TZ).date() + timedelta(days=1)).strftime('%d.%m.%Y')
    text = f'Графік на {day}\nЛитовеж — 4.2; Нововолинськ — 2.2.\nПеревірте актуальні години на офіційній сторінці: {SCHEDULE_URL}\nАвтоматичне зчитування годин ще перевіряється.'
    for chat in context.application.bot_data.get('chats', set()):
        try: await context.bot.send_message(chat_id=chat, text=text, disable_web_page_preview=True)
        except Exception: logging.exception('Send failed')

def main():
    if not TOKEN:
        raise RuntimeError('Set TELEGRAM_BOT_TOKEN in Railway Variables before starting')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start)); app.add_handler(CommandHandler('status', status))
    app.job_queue.run_repeating(poll, interval=300, first=3)
    app.job_queue.run_daily(tomorrow, time=time(23, 0, tzinfo=TZ))
    app.run_polling()

if __name__ == '__main__': main()

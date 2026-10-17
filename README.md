# Volynoblenergo outage Telegram bot

Monitors official Volynoblenergo sources for:
- Lytovizh, queue **4.2**
- Novovolynsk, queue **2.2**

Official sources:
- Schedule: https://energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/hrafik-vidkliuchen/
- Current/planned outage notices: https://www.energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/chomu-nemaie-elektropostachannia/
- Embedded queue widget (needs verification): https://voe-poweron.inneti.net/schedule_queues

## Important status and limitations

The service is scaffolded for Railway, with a Dockerfile, persistent state path, five-minute source polling and a 23:00 Europe/Kyiv daily message. **It is not yet a verified outage alert system.** The schedule widget's exact data format and the date/hour extraction still need validation against live official output. Until then the bot intentionally does not invent schedule hours or claim a planned queue schedule confirms an actual outage/restoration.

Polling every five minutes detects source changes only after the source publishes them. The official schedule may update much less frequently.

## Configure Telegram

1. In Telegram, open **@BotFather**, run `/newbot`, and complete its prompts.
2. Copy the bot token. Never commit it to GitHub or post it in a chat.
3. In Railway → project `volynoblenergo-alerts` → service `outage-telegram-bot` → Variables, add:
   - `TELEGRAM_BOT_TOKEN` = token from BotFather
   - `STATE_FILE` = `/data/state.json`
   - `CHECK_EVERY_SECONDS` = `300`
4. Open your bot in Telegram and press **Start** or send `/start`.
5. Use `/status`, `/today`, and `/tomorrow` to inspect current bot status and source links.

The Railway service has a persistent volume mounted at `/data`, so registered chat IDs and local state survive restarts.

## Runtime

The service uses the Playwright Python 1.56.0 image and polls official pages every five minutes. It is configured for restart-on-failure and is intended to run continuously, not as a cron job.

## Security

Do not store bot tokens in this repository. Configure them as Railway service variables. If the token is ever exposed, revoke it with @BotFather and set the replacement in Railway.

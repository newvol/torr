# Volynoblenergo outage notifications bot

Cloud-hosted Telegram bot for monitoring the official Volynoblenergo hourly outage schedules for subqueues 4.2 (Lytovizh) and 2.2 (Novovolynsk).

## Status

Initial repository scaffold. Do not treat as production-ready until the official schedule payload is parsed and verified against the live page. The official published graph says it updates hourly, so polling every five minutes will detect source changes but cannot make the source itself update faster.

Official schedule page: https://energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/hrafik-vidkliuchen/
Official outage events page: https://www.energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/chomu-nemaie-elektropostachannia/

Planned features:
- Poll schedule data every 5 minutes.
- Notify Telegram subscribers when today's or tomorrow's official schedule changes.
- Send tomorrow's schedule at 23:00 Europe/Kyiv.
- Track planned and emergency outage announcements where official structured data is available.

## Configuration

Use environment variables for Telegram bot token and allowed chat IDs. Never commit secrets.

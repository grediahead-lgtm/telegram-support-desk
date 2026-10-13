# telegram-support-desk

A small Telegram support desk for a small business: customers write to your bot, each conversation becomes a numbered ticket in your team's chat, and your reply goes back to the customer. Python standard library only, no database, no web server.

## What it does
- A customer writes to the bot in a private chat. The first message opens ticket `#N` and is forwarded to the **staff chat** (a group or your own chat). The customer gets one "received" confirmation. Further messages go to the same open ticket.
- Staff **reply to the forwarded message** and the answer is delivered to the customer. Or use `/reply N text`.
- Staff commands: `/open` (open tickets), `/ticket N` (last messages), `/reply N text`, `/close N`, `/reopen N`. Customer commands: `/status`, `/close`.
- If the customer blocked the bot, staff see "could not deliver" instead of a silent loss. If forwarding to staff fails, the ticket is still saved and shown by `/open`.
- Private customer chats only; groups and other bots are ignored (except the one staff chat). Rate limit 20 messages a minute per customer, messages cut to 1000 characters, plain text only, so no markup injection.
- Data is one JSON file (`tickets.json`, written atomically). The bot token comes only from `TELEGRAM_BOT_TOKEN`; message texts are not logged.

## Quick start
1. Create a bot with @BotFather. Create a Telegram group for your team, add the bot, and find the group's chat id (a negative number). In a group, make the bot an admin or turn off its privacy mode in BotFather, otherwise it will not see plain replies.
2. `cp examples/config.example.json config.json`, set `staff_chat_id` and edit the texts.
3. Check, then run:
```bash
PYTHONPATH=src python3 -m support_desk --config config.json --check
TELEGRAM_BOT_TOKEN=123456:your-token PYTHONPATH=src python3 -m support_desk --config config.json
```
Tests: `python3 -m unittest discover -s tests` (no internet, no real token).

## Limits (read this)
- **Everyone in the staff chat is staff.** Anyone who can write there can answer customers and close tickets. There are no roles and no assignment of tickets to people.
- Only text. Photos, files, voice messages and stickers from customers are ignored, not forwarded.
- One open ticket per customer; a customer cannot open a second topic until the first is closed.
- No working-hours logic, no automatic closing, no statistics, no search over old tickets.
- A JSON file suits one small team, not thousands of tickets a day. Not tested against the real Telegram servers in an automated way; the ticket logic, storage and message handling are. Try it with your own test bot and a test group first.
- Single process: do not run two copies on the same file.

MIT license.

---

# telegram-support-desk (українською)

Невеликий центр підтримки в Telegram: клієнт пише боту, кожна розмова стає тікетом `#N` у чаті вашої команди, а відповідь співробітника повертається клієнту. Лише стандартна бібліотека Python.

**Запуск:** `cp examples/config.example.json config.json`, вкажіть `staff_chat_id`, `--check`, потім із `TELEGRAM_BOT_TOKEN`. Співробітник відповідає, роблячи reply на повідомлення тікета, або командою `/reply N текст`.

**Важливо:** усі учасники чату команди вважаються співробітниками (ролей немає); лише текст; один відкритий тікет на клієнта; JSON-файл підходить для малої команди. З реальним Telegram автоматично не тестувалося.

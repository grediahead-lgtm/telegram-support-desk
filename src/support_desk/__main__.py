import argparse
import json
import os
import sys
import time

from .core import SupportDesk
from .store import TicketStore
from .telegram_api import TelegramClient

NEED = ["greeting", "received", "status_open", "status_none", "closed_by_you", "staff_help", "no_open", "bad_ticket",
        "staff_closed", "staff_reopened", "reply_hint", "ticket_closed", "from_staff", "not_delivered", "delivered"]


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg.get("staff_chat_id"), int):
        raise ValueError("config needs staff_chat_id (a number)")
    miss = [k for k in NEED if not cfg.get("texts", {}).get(k)]
    if miss:
        raise ValueError("config.texts is missing: " + ", ".join(miss))
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(prog="support_desk")
    ap.add_argument("--config", required=True)
    ap.add_argument("--data", default="tickets.json")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    store = TicketStore(args.data)
    if args.check:
        print("config ok, open tickets:", len(store.open_tickets()))
        return 0
    client = TelegramClient(os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    desk = SupportDesk(cfg, store, client.send)
    offset = 0
    while True:
        try:
            for upd in client.updates(offset):
                offset = upd["update_id"] + 1
                if upd.get("message"):
                    try:
                        desk.handle(upd["message"])
                    except Exception as e:  # one bad message must not stop the bot
                        print("handler error:", type(e).__name__, file=sys.stderr)
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print("error:", type(e).__name__, file=sys.stderr)
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())

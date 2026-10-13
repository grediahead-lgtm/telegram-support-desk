import datetime as dt
import re
import time

MAX_TEXT = 1000


def clean(s, n=MAX_TEXT):
    return re.sub(r"[ \t]+", " ", re.sub(r"\r", "", s or "")).strip()[:n]


def display_name(user):
    name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x)
    name = clean(name, 40) or "customer"
    return name + (" @" + clean(user["username"], 32) if user.get("username") else "")


class SupportDesk:
    """Customer private chat <-> one staff chat. `send(chat_id, text)` must return the message_id (or raise)."""

    def __init__(self, cfg, store, send, now=None, rate_limit=20):
        self.cfg, self.store, self.send = cfg, store, send
        self.staff_chat = cfg["staff_chat_id"]
        self.now = now or dt.datetime.now
        self._hits, self.rate_limit = {}, rate_limit

    def _stamp(self):
        return self.now().strftime("%Y-%m-%d %H:%M")

    def _limited(self, chat):
        t = time.monotonic()
        h = [x for x in self._hits.get(chat, []) if t - x < 60] + [t]
        self._hits[chat] = h
        return len(h) > self.rate_limit

    def handle(self, m):
        """m: a Telegram `message` dict. Returns nothing; all output goes through self.send."""
        chat = m.get("chat", {})
        user = m.get("from", {})
        text = clean(m.get("text"))
        if user.get("is_bot") or not text:
            return
        if chat.get("id") == self.staff_chat:
            self._staff(text, (m.get("reply_to_message") or {}).get("message_id"))
        elif chat.get("type") == "private":
            if not self._limited(chat["id"]):
                self._customer(chat["id"], user, text)

    # ---- customer side ----
    def _customer(self, chat, user, text):
        t = self.cfg["texts"]
        cmd = text.split(" ")[0].lower() if text.startswith("/") else ""
        if cmd in ("/start", "/help"):
            return self.send(chat, t["greeting"])
        if cmd == "/status":
            tk = self.store.open_of_chat(chat)
            return self.send(chat, t["status_open"].format(id=tk["id"]) if tk else t["status_none"])
        if cmd == "/close":
            tk = self.store.open_of_chat(chat)
            if not tk:
                return self.send(chat, t["status_none"])
            self.store.set_status(tk["id"], "closed")
            self._to_staff(tk, "Ticket #%d closed by the customer." % tk["id"])
            return self.send(chat, t["closed_by_you"].format(id=tk["id"]))
        if cmd:
            return self.send(chat, t["greeting"])
        tk = self.store.open_of_chat(chat)
        new = tk is None
        if new:
            tk = self.store.create(chat, display_name(user), self._stamp())
        self.store.add_message(tk["id"], "customer", text, self._stamp())
        self._to_staff(tk, "#%d %s%s:\n%s" % (tk["id"], tk["name"], "" if new else " (open)", text))
        if new:
            self.send(chat, t["received"].format(id=tk["id"]))

    def _to_staff(self, tk, text):
        try:
            mid = self.send(self.staff_chat, text)
        except Exception:
            return  # the ticket is saved; staff can still see it with /open
        if mid is not None:
            self.store.link(mid, tk["id"])

    # ---- staff side ----
    def _staff(self, text, reply_to):
        t = self.cfg["texts"]
        cmd, _, rest = text.partition(" ")
        cmd = cmd.lower().split("@")[0]
        if cmd in ("/start", "/help"):
            return self.send(self.staff_chat, t["staff_help"])
        if cmd == "/open":
            rows = self.store.open_tickets()
            if not rows:
                return self.send(self.staff_chat, t["no_open"])
            return self.send(self.staff_chat, "\n".join(
                "#%d %s: %s" % (x["id"], x["name"], (x["messages"][-1]["text"] if x["messages"] else "")[:60]) for x in rows[:30]))
        if cmd in ("/ticket", "/close", "/reopen", "/reply"):
            num, _, body = rest.strip().partition(" ")
            if not num.isdigit() or not self.store.get(int(num)):
                return self.send(self.staff_chat, t["bad_ticket"])
            tk = self.store.get(int(num))
            if cmd == "/ticket":
                hist = "\n".join("%s %s: %s" % (x["at"], "C" if x["from"] == "customer" else "S", x["text"][:200]) for x in tk["messages"][-15:])
                return self.send(self.staff_chat, "#%d %s (%s)\n%s" % (tk["id"], tk["name"], tk["status"], hist))
            if cmd == "/close":
                self.store.set_status(tk["id"], "closed")
                return self.send(self.staff_chat, t["staff_closed"].format(id=tk["id"]))
            if cmd == "/reopen":
                self.store.set_status(tk["id"], "open")
                return self.send(self.staff_chat, t["staff_reopened"].format(id=tk["id"]))
            return self._answer(tk, clean(body))
        if cmd.startswith("/"):
            return self.send(self.staff_chat, t["staff_help"])
        # a plain message: only a reply to a forwarded ticket message goes to a customer
        tid = self.store.ticket_of_message(reply_to) if reply_to else None
        tk = self.store.get(tid) if tid else None
        if tk is None:
            return self.send(self.staff_chat, t["reply_hint"])
        self._answer(tk, text)

    def _answer(self, tk, text):
        t = self.cfg["texts"]
        if not text:
            return self.send(self.staff_chat, t["reply_hint"])
        if tk["status"] != "open":
            return self.send(self.staff_chat, t["ticket_closed"].format(id=tk["id"]))
        try:
            self.send(tk["chat_id"], t["from_staff"].format(text=text))
        except Exception:
            return self.send(self.staff_chat, t["not_delivered"].format(id=tk["id"]))
        self.store.add_message(tk["id"], "staff", text, self._stamp())
        self.send(self.staff_chat, t["delivered"].format(id=tk["id"]))

import datetime as dt
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

from support_desk.__main__ import load_config  # noqa: E402
from support_desk.core import SupportDesk, clean, display_name  # noqa: E402
from support_desk.store import TicketStore  # noqa: E402

CFG = load_config(os.path.join(ROOT, "examples", "config.example.json"))
STAFF = CFG["staff_chat_id"]
NOW = dt.datetime(2026, 10, 13, 10, 0)


class Sender:
    def __init__(self):
        self.log, self.next_id, self.fail_for = [], 100, set()

    def __call__(self, chat, text):
        if chat in self.fail_for:
            raise RuntimeError("blocked")
        self.next_id += 1
        self.log.append((chat, text, self.next_id))
        return self.next_id

    def to(self, chat):
        return [x[1] for x in self.log if x[0] == chat]


def customer(chat, text, name="Anna"):
    return {"chat": {"id": chat, "type": "private"}, "from": {"id": chat, "first_name": name}, "text": text}


def staff(text, reply_to=None):
    m = {"chat": {"id": STAFF, "type": "supergroup"}, "from": {"id": 7, "first_name": "Op"}, "text": text}
    if reply_to:
        m["reply_to_message"] = {"message_id": reply_to}
    return m


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.path = os.path.join(self.d.name, "t.json")
        self.snd = Sender()
        self.store = TicketStore(self.path)
        self.desk = SupportDesk(CFG, self.store, self.snd, now=lambda: NOW)


class CustomerTests(Base):
    def test_first_message_creates_ticket_and_forwards(self):
        self.desk.handle(customer(1, "Where is my order?"))
        self.assertEqual(len(self.store.open_tickets()), 1)
        self.assertIn("#1 Anna:\nWhere is my order?", self.snd.to(STAFF)[0])
        self.assertIn("#1", self.snd.to(1)[0])

    def test_second_message_goes_to_same_ticket_without_new_ack(self):
        self.desk.handle(customer(1, "Hello"))
        self.desk.handle(customer(1, "One more detail"))
        self.assertEqual(len(self.store.tickets), 1)
        self.assertEqual(len(self.store.tickets[0]["messages"]), 2)
        self.assertEqual(len(self.snd.to(1)), 1)  # only one "received"
        self.assertEqual(len(self.snd.to(STAFF)), 2)

    def test_two_customers_two_tickets(self):
        self.desk.handle(customer(1, "A"))
        self.desk.handle(customer(2, "B", name="Boris"))
        self.assertEqual([t["chat_id"] for t in self.store.tickets], [1, 2])

    def test_close_then_new_ticket(self):
        self.desk.handle(customer(1, "A"))
        self.desk.handle(customer(1, "/close"))
        self.assertEqual(self.store.tickets[0]["status"], "closed")
        self.desk.handle(customer(1, "B"))
        self.assertEqual(len(self.store.tickets), 2)

    def test_status_and_unknown_command(self):
        self.desk.handle(customer(1, "/status"))
        self.assertIn("no open", self.snd.to(1)[-1])
        self.desk.handle(customer(1, "A"))
        self.desk.handle(customer(1, "/status"))
        self.assertIn("#1", self.snd.to(1)[-1])
        self.desk.handle(customer(1, "/whatever"))
        self.assertIn("Hello", self.snd.to(1)[-1])
        self.assertEqual(len(self.store.tickets), 1)  # a command is not a ticket message

    def test_groups_and_bots_are_ignored(self):
        self.desk.handle({"chat": {"id": -5, "type": "group"}, "from": {"id": 9, "first_name": "X"}, "text": "hi"})
        bot = customer(3, "hi")
        bot["from"]["is_bot"] = True
        self.desk.handle(bot)
        self.desk.handle(customer(4, "   "))
        self.assertEqual(self.snd.log, [])

    def test_rate_limit(self):
        d = SupportDesk(CFG, self.store, self.snd, now=lambda: NOW, rate_limit=3)
        for i in range(10):
            d.handle(customer(1, "msg %d" % i))
        self.assertEqual(len(self.store.tickets[0]["messages"]), 3)

    def test_long_text_is_cut_and_markup_stays_plain(self):
        self.desk.handle(customer(1, "<b>x</b> " + "a" * 5000))
        self.assertEqual(len(self.store.tickets[0]["messages"][0]["text"]), 1000)
        self.assertTrue(self.store.tickets[0]["messages"][0]["text"].startswith("<b>x</b>"))

    def test_staff_forward_failure_keeps_ticket(self):
        self.snd.fail_for.add(STAFF)
        self.desk.handle(customer(1, "Help"))
        self.assertEqual(len(self.store.open_tickets()), 1)

    def test_display_name(self):
        self.assertEqual(display_name({"first_name": "Ann", "last_name": "Lee", "username": "al"}), "Ann Lee @al")
        self.assertEqual(display_name({}), "customer")
        self.assertEqual(clean("a\r\n  b"), "a\n b")


class StaffTests(Base):
    def open_ticket(self):
        self.desk.handle(customer(1, "Where is my order?"))
        return [x for x in self.snd.log if x[0] == STAFF][-1][2]  # message_id of the forwarded ticket

    def test_reply_to_forwarded_message_reaches_customer(self):
        mid = self.open_ticket()
        self.desk.handle(staff("It ships today", reply_to=mid))
        self.assertEqual(self.snd.to(1)[-1], "Support: It ships today")
        self.assertEqual(self.store.tickets[0]["messages"][-1]["from"], "staff")
        self.assertIn("Sent to ticket #1", self.snd.to(STAFF)[-1])

    def test_plain_message_without_reply_is_not_sent(self):
        self.open_ticket()
        before = len(self.snd.to(1))
        self.desk.handle(staff("just chatting"))
        self.assertEqual(len(self.snd.to(1)), before)
        self.assertIn("reply to the ticket message", self.snd.to(STAFF)[-1])

    def test_reply_command_and_bad_number(self):
        self.open_ticket()
        self.desk.handle(staff("/reply 1 Check your email"))
        self.assertEqual(self.snd.to(1)[-1], "Support: Check your email")
        self.desk.handle(staff("/reply 99 hi"))
        self.assertIn("not found", self.snd.to(STAFF)[-1])
        self.desk.handle(staff("/reply abc hi"))
        self.assertIn("not found", self.snd.to(STAFF)[-1])

    def test_open_list_close_reopen(self):
        self.open_ticket()
        self.desk.handle(staff("/open"))
        self.assertIn("#1 Anna", self.snd.to(STAFF)[-1])
        self.desk.handle(staff("/close 1"))
        self.desk.handle(staff("/open"))
        self.assertIn("No open tickets", self.snd.to(STAFF)[-1])
        self.desk.handle(staff("/reply 1 hi"))
        self.assertIn("closed", self.snd.to(STAFF)[-1])
        self.desk.handle(staff("/reopen 1"))
        self.desk.handle(staff("/reply 1 hi again"))
        self.assertEqual(self.snd.to(1)[-1], "Support: hi again")

    def test_ticket_history(self):
        self.open_ticket()
        self.desk.handle(staff("/reply 1 on it"))
        self.desk.handle(staff("/ticket 1"))
        out = self.snd.to(STAFF)[-1]
        self.assertIn("C: Where is my order?", out)
        self.assertIn("S: on it", out)

    def test_undeliverable_customer_is_reported(self):
        mid = self.open_ticket()
        self.snd.fail_for.add(1)
        self.desk.handle(staff("hello", reply_to=mid))
        self.assertIn("Could not deliver", self.snd.to(STAFF)[-1])
        self.assertEqual(self.store.tickets[0]["messages"][-1]["from"], "customer")

    def test_staff_commands_with_bot_suffix(self):
        self.desk.handle(staff("/open@my_support_bot"))
        self.assertIn("No open tickets", self.snd.to(STAFF)[-1])

    def test_customer_close_notifies_staff(self):
        self.open_ticket()
        self.desk.handle(customer(1, "/close"))
        self.assertIn("closed by the customer", self.snd.to(STAFF)[-1])


class StoreTests(Base):
    def test_persistence_and_link_trim(self):
        self.desk.handle(customer(1, "A"))
        again = TicketStore(self.path)
        self.assertEqual(len(again.tickets), 1)
        self.assertEqual(again.ticket_of_message(101), 1)
        from support_desk import store as st
        old = st.MAX_LINKS
        st.MAX_LINKS = 3
        try:
            for i in range(10):
                again.link(1000 + i, 1)
            self.assertEqual(len(again.links), 3)
        finally:
            st.MAX_LINKS = old

    def test_config_validation(self):
        import json
        bad = os.path.join(self.d.name, "c.json")
        with open(bad, "w") as f:
            json.dump({"staff_chat_id": "x", "texts": {}}, f)
        with self.assertRaises(ValueError):
            load_config(bad)


if __name__ == "__main__":
    unittest.main()

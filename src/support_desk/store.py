import json
import os

MAX_LINKS = 2000


class TicketStore:
    """Tickets in one JSON file, written atomically. Fine for a small team; not for thousands of tickets a day."""

    def __init__(self, path):
        self.path = path
        self.tickets = []
        self.links = {}  # staff-chat message_id (str) -> ticket id
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.tickets, self.links = data["tickets"], data["links"]

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"tickets": self.tickets, "links": self.links}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get(self, tid):
        for t in self.tickets:
            if t["id"] == tid:
                return t
        return None

    def open_of_chat(self, chat_id):
        for t in self.tickets:
            if t["chat_id"] == chat_id and t["status"] == "open":
                return t
        return None

    def open_tickets(self):
        return [t for t in self.tickets if t["status"] == "open"]

    def create(self, chat_id, name, at):
        t = {"id": max([x["id"] for x in self.tickets] + [0]) + 1, "chat_id": chat_id, "name": name,
             "status": "open", "created": at, "messages": []}
        self.tickets.append(t)
        self._save()
        return t

    def add_message(self, tid, who, text, at):
        self.get(tid)["messages"].append({"from": who, "text": text, "at": at})
        self._save()

    def set_status(self, tid, status):
        t = self.get(tid)
        if t is None:
            return None
        t["status"] = status
        self._save()
        return t

    def link(self, message_id, tid):
        self.links[str(message_id)] = tid
        if len(self.links) > MAX_LINKS:
            for k in list(self.links)[: len(self.links) - MAX_LINKS]:
                del self.links[k]
        self._save()

    def ticket_of_message(self, message_id):
        return self.links.get(str(message_id))

"""iMessage in and out. Two backends behind one interface:

BlueBubbles  - BlueBubbles Server on a Mac signed in to Messages. Webhook: Settings > API &
               Webhooks > add  <PUBLIC_URL>/webhook?token=<WINGMAN_WEBHOOK_TOKEN>, event "New Messages".
               Sends with the server's REST API (BB_URL + BB_PASSWORD).
Sendblue     - hosted iMessage numbers. Receive webhook = the same URL; sends with the API key pair.

parse(payload) -> [Inbound]; fetch(ref) -> bytes; send(chat, text)."""
import uuid
from dataclasses import dataclass, field

import httpx

from . import config


@dataclass
class Inbound:
    guid: str
    sender: str            # phone / Apple ID of whoever sent it (lowercased)
    chat: str              # where to reply: BlueBubbles chat guid / Sendblue phone number
    text: str
    attachments: list = field(default_factory=list)   # refs for fetch()
    from_me: bool = False


class BlueBubbles:
    name = "bluebubbles"

    def parse(self, payload: dict) -> list:
        if (payload or {}).get("type") != "new-message":
            return []
        d = payload.get("data") or {}
        chats = d.get("chats") or []
        handle = (d.get("handle") or {}).get("address") or ""
        atts = [a.get("guid") for a in d.get("attachments") or []
                if a.get("guid") and str(a.get("mimeType") or "image/").startswith("image/")]
        return [Inbound(guid=d.get("guid") or "", sender=handle.lower(),
                        chat=(chats[0].get("guid") if chats else "") or "",
                        text=(d.get("text") or "").replace("￼", "").strip(),
                        attachments=atts, from_me=bool(d.get("isFromMe")))]

    def fetch(self, ref: str) -> bytes:
        r = httpx.get(f"{config.BB_URL}/api/v1/attachment/{ref}/download",
                      params={"password": config.BB_PASSWORD}, timeout=60)
        r.raise_for_status()
        return r.content

    def send(self, chat: str, text: str):
        r = httpx.post(f"{config.BB_URL}/api/v1/message/text", params={"password": config.BB_PASSWORD},
                       json={"chatGuid": chat, "tempGuid": str(uuid.uuid4()), "message": text,
                             "method": config.BB_METHOD}, timeout=60)
        r.raise_for_status()


class Sendblue:
    name = "sendblue"

    def parse(self, payload: dict) -> list:
        d = payload or {}
        if d.get("is_outbound") or not d.get("from_number"):
            return []
        num = str(d["from_number"]).lower()
        return [Inbound(guid=d.get("message_handle") or "", sender=num, chat=num,
                        text=(d.get("content") or "").strip(),
                        attachments=[d["media_url"]] if d.get("media_url") else [])]

    def fetch(self, ref: str) -> bytes:
        r = httpx.get(ref, timeout=60, follow_redirects=True)
        r.raise_for_status()
        return r.content

    def send(self, chat: str, text: str):
        body = {"number": chat, "content": text}
        if config.SB_FROM_NUMBER:
            body["from_number"] = config.SB_FROM_NUMBER
        r = httpx.post(config.SB_URL, json=body, timeout=60,
                       headers={"sb-api-key-id": config.SB_API_KEY, "sb-api-secret-key": config.SB_API_SECRET})
        r.raise_for_status()


def get():
    return Sendblue() if config.TRANSPORT == "sendblue" else BlueBubbles()

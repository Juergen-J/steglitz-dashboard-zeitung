"""Liest den Anmeldecode des Dashboards aus dem IMAP-Postfach.

Das Dashboard schickt eine Mail mit dem Betreff
"Dein Anmeldecode lautet 123456".
"""
from __future__ import annotations

import email
import imaplib
import re
import time
from email.header import decode_header, make_header

from .config import Config

CODE_RE = re.compile(r"Anmeldecode lautet\s*(\d{6})")
# Body: "Dein Anmeldecode lautet:\n\n306262"
BODY_CODE_RE = re.compile(r"Anmeldecode lautet:?\s*(?:<[^>]+>\s*)*(\d{6})")


def _body_text(msg: email.message.Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    out = []
    for p in parts:
        if p.get_content_type() in ("text/plain", "text/html"):
            payload = p.get_payload(decode=True) or b""
            out.append(payload.decode(p.get_content_charset() or "utf-8", errors="replace"))
    return "\n".join(out)


class MailCodeError(RuntimeError):
    pass


class CodeMailbox:
    def __init__(self, cfg: Config):
        if not cfg.imap_password:
            raise MailCodeError("IMAP_PASSWORD fehlt (im Profil bzw. in .env)")
        self.cfg = cfg
        self.imap = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
        self.imap.login(cfg.imap_user, cfg.imap_password)
        typ, _ = self.imap.select(cfg.imap_folder)
        if typ != "OK":
            raise MailCodeError(f"Ordner {cfg.imap_folder} nicht gefunden")
        self.baseline_uid = self._max_uid()

    def _max_uid(self) -> int:
        typ, data = self.imap.uid("SEARCH", None, "ALL")
        uids = [int(x) for x in (data[0] or b"").split()]
        return max(uids) if uids else 0

    def wait_for_code(self, timeout: float = 180, interval: float = 4) -> str:
        """Wartet auf eine NEUE Code-Mail (nach dem Öffnen des Postfachs)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.imap.noop()
            typ, data = self.imap.uid("SEARCH", None, f"UID {self.baseline_uid + 1}:*", "SUBJECT", "Anmeldecode")
            uids = sorted((int(x) for x in (data[0] or b"").split()), reverse=True)
            for uid in uids:
                if uid <= self.baseline_uid:
                    continue
                typ, msg_data = self.imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
                raw = msg_data[0][1] if msg_data and msg_data[0] else b""
                msg = email.message_from_bytes(raw)
                subject = str(make_header(decode_header(msg.get("Subject", ""))))
                m = CODE_RE.search(subject) or BODY_CODE_RE.search(_body_text(msg))
                if m:
                    if self.cfg.imap_delete_code_mail:
                        self.imap.uid("STORE", str(uid), "+FLAGS", r"(\Deleted)")
                        self.imap.expunge()
                    return m.group(1)
            time.sleep(interval)
        raise MailCodeError("Keine Code-Mail innerhalb der Wartezeit erhalten")

    def close(self) -> None:
        try:
            self.imap.close()
            self.imap.logout()
        except Exception:
            pass

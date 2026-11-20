"""Client für das Schul-Dashboard (github.com/specht/schul-dashboard).

Login:   POST /api/login {email}           -> {tag}
         Code kommt per Mail
         POST /api/confirm_login {tag,code} -> Cookie `sid` (1 Jahr gültig)
Daten:   /gen/w/<id>/<YYYY-WW>.json.gz     Stundenplan einer Woche
         /gen/w/<id>/homework.json.gz       Hausaufgaben der nächsten 7 Tage
         /gen/w/<id>/messages.json.gz       Nachrichten / Kommentare
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import Config
from ..mailcode import CodeMailbox

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


class DashboardError(RuntimeError):
    pass


class ServerDown(DashboardError):
    pass


def week_key(d: dt.date) -> str:
    monday = d - dt.timedelta(days=d.weekday())
    y, w, _ = monday.isocalendar()
    return f"{y}-{w:02d}"


class DashboardClient:
    def __init__(self, cfg: Config, log=print):
        self.cfg = cfg
        self.log = log
        self.http = httpx.Client(
            base_url=cfg.dashboard_url,
            headers={"User-Agent": UA},
            follow_redirects=True,
            timeout=30,
        )
        self._load_session()
        self._home_html: str | None = None

    # ---------- Session ----------
    def _load_session(self) -> None:
        f = self.cfg.session_file
        if f.exists():
            for name, value in json.loads(f.read_text()).items():
                self.http.cookies.set(name, value, domain=httpx.URL(self.cfg.dashboard_url).host)

    def _save_session(self) -> None:
        f = self.cfg.session_file
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({c.name: c.value for c in self.http.cookies.jar}))
        f.chmod(0o600)

    def _send(self, method: str, path: str, **kw) -> httpx.Response:
        """Anfrage mit Wiederholung, wenn der Server kurz weg ist (5xx / Netzwerk)."""
        waits = [10, 30, 60]
        for attempt in range(len(waits) + 1):
            try:
                r = self.http.request(method, path, **kw)
                if r.status_code < 500:
                    return r
                problem = f"HTTP {r.status_code}"
            except httpx.TransportError as exc:
                problem = type(exc).__name__
            if attempt == len(waits):
                break
            self.log(f"⏳ Dashboard antwortet nicht ({problem}), neuer Versuch in {waits[attempt]} s …")
            time.sleep(waits[attempt])
        raise ServerDown(f"Dashboard nicht erreichbar ({problem}) – später nochmal versuchen")

    def _api(self, path: str, data: dict) -> dict:
        r = self._send("POST", path, content=json.dumps(data), headers={"Content-Type": "application/json"})
        if r.status_code != 200:
            raise DashboardError(f"{path}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()

    def is_logged_in(self) -> bool:
        if "sid" not in self.http.cookies:
            return False
        r = self._send("GET", "/")  # 5xx -> ServerDown, NICHT neu einloggen
        self._home_html = r.text
        return "timetable_id" in r.text and "id='email'" not in r.text

    def login(self) -> None:
        if not self.cfg.dashboard_email:
            raise DashboardError("DASHBOARD_EMAIL fehlt (im Profil bzw. in .env)")
        self.log("🔐 Nicht eingeloggt – fordere Code an …")
        box = CodeMailbox(self.cfg)  # vor dem Anfordern öffnen, damit nur neue Mails zählen
        try:
            res = self._api("/api/login", {"email": self.cfg.dashboard_email, "return_to": ""})
            if "tag" not in res:
                raise DashboardError(f"Login abgelehnt: {res.get('error', res)}")
            self.log("📬 Warte auf Code-Mail …")
            code = box.wait_for_code()
        finally:
            box.close()
        self.log("🔑 Code erhalten, bestätige …")
        res = self._api("/api/confirm_login", {"tag": res["tag"], "code": code})
        if res.get("error"):
            raise DashboardError(f"Code abgelehnt: {res['error']}")
        if res.get("force_2fa"):
            raise DashboardError("Dashboard verlangt 2FA – wird (noch) nicht unterstützt")
        if "sid" not in self.http.cookies:
            raise DashboardError("Kein Session-Cookie erhalten")
        self._save_session()
        self.log("✅ Eingeloggt, Session gespeichert")

    def ensure_login(self) -> None:
        if not self.is_logged_in():
            self.login()
            if not self.is_logged_in():
                raise DashboardError("Login scheint nicht geklappt zu haben")
        self._save_session()

    # ---------- Daten ----------
    def home_html(self) -> str:
        if self._home_html is None:
            self._home_html = self._send("GET", "/").text
        return self._home_html

    def user_id(self) -> str:
        html = self.home_html()
        m = re.search(r"var\s+timetable_id\s*=\s*'([^']+)'", html)
        if not m:
            html = self._send("GET", "/timetable").text
            m = re.search(r"var\s+timetable_id\s*=\s*'([^']+)'", html)
        if not m:
            raise DashboardError("timetable_id nicht gefunden")
        return m.group(1)

    def _gz_text(self, path: str) -> str | None:
        r = self._send("GET", path)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        raw = r.content
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass  # bereits per Content-Encoding entpackt
        return raw.decode("utf-8", errors="replace")

    def _gz_json(self, path: str) -> Any:
        text = self._gz_text(path)
        return None if text is None else json.loads(text)

    def fetch_all(self, target: dt.date, raw_dir: Path | None = None) -> dict:
        uid = self.user_id()
        # Vorwoche: dort aufgegebene Hausaufgaben; Folgewoche: Ausblick
        weeks = sorted({week_key(target + dt.timedelta(days=n)) for n in (-7, 0, 7)})
        messages = self._gz_json(f"/gen/w/{uid}/messages.json.gz") or []
        cutoff = (target - dt.timedelta(days=7)).isoformat()
        for m in messages[:40]:
            mid = m.get("mid")
            if mid and m.get("date", "") >= cutoff:
                m["html"] = self._gz_text(f"/gen/m/{mid[:2]}/{mid[2:]}.html.gz")
        data = {
            "user_id": uid,
            "weeks": {wk: self._gz_json(f"/gen/w/{uid}/{wk}.json.gz") for wk in weeks},
            "homework": self._gz_json(f"/gen/w/{uid}/homework.json.gz") or [],
            "messages": messages,
            "home_html": self.home_html(),
        }
        if raw_dir:
            raw_dir.mkdir(parents=True, exist_ok=True)
            for k, v in data.items():
                if k == "home_html":
                    (raw_dir / "home.html").write_text(v)
                else:
                    (raw_dir / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False, indent=2))
        return data

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Schultermine, die für Schüler:innen uninteressant sind (Regex, Groß/klein egal)
DEFAULT_EVENT_EXCLUDE = (
    r"Fachkonferenz|Klassenteamsitzung|Klassenkonferenz|Gesamtkonferenz|F\(B\)L"
    r"|Dienstbesprechung|Fachbereich|Lehrerkonferenz|Schulkonferenz"
)


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "ja", "on")


@dataclass
class Config:
    profile: str
    dashboard_url: str
    dashboard_email: str
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    imap_folder: str
    imap_delete_code_mail: bool
    newspaper_title: str
    student_name: str
    comic_style: str
    next_day_after_hour: int
    printer: str
    print_color: bool
    event_exclude: str
    hide_subjects: list[str]
    comic_styles: list[str]
    mascot: str
    variety: bool
    edition: str
    openai_api_key: str
    openai_model: str
    ai_content: str
    data_dir: Path
    out_dir: Path

    @property
    def profile_slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "_", self.dashboard_email.lower()).strip("_") or "default"

    @property
    def ai_enabled(self) -> bool:
        """auto = an, sobald ein API-Key gesetzt ist."""
        if self.ai_content in ("0", "false", "no", "off", "aus"):
            return False
        return bool(self.openai_api_key)

    @property
    def session_file(self) -> Path:
        return self.data_dir / "sessions" / f"{self.profile_slug}.json"


PROFILES_DIR = PROJECT_ROOT / "profiles"

# Persönliche Schlüssel: werden bei einem Profil NIE aus der Basis-.env übernommen.
# (Alle anderen Schlüssel, z. B. COMIC_STYLE oder PRINTER, darf ein Profil optional überschreiben.)
STUDENT_KEYS = ("DASHBOARD_EMAIL", "STUDENT_NAME", "IMAP_USER", "IMAP_PASSWORD", "HIDE_SUBJECTS")


def list_profiles() -> list[str]:
    return sorted(p.stem for p in PROFILES_DIR.glob("*.env"))


def load_config(env_file: str | None = None, profile: str | None = None) -> Config:
    """Basis-.env + optional profiles/<profile>.env (überschreibt die Basis)."""
    base = Path(env_file) if env_file else PROJECT_ROOT / ".env"
    values: dict[str, str | None] = dotenv_values(base) if base.exists() else {}
    if profile:
        pfile = PROFILES_DIR / f"{profile}.env"
        if not pfile.exists():
            raise FileNotFoundError(f"Profil nicht gefunden: {pfile}")
        for k in STUDENT_KEYS:
            values.pop(k, None)
        values.update({k: v for k, v in dotenv_values(pfile).items() if v not in (None, "")})

    def e(key: str) -> str | None:
        v = values.get(key)
        return v if v not in (None, "") else os.environ.get(key)

    email = (e("DASHBOARD_EMAIL") or "").strip()
    name = (e("STUDENT_NAME") or "").strip()
    if not name and email:
        name = email.split("@")[0].split(".")[0].capitalize()
    return Config(
        profile=profile or "",
        dashboard_url=(e("DASHBOARD_URL") or "https://dashboard.gymnasiumsteglitz.de").rstrip("/"),
        dashboard_email=email,
        imap_host=e("IMAP_HOST") or "imap.ionos.de",
        imap_port=int(e("IMAP_PORT") or 993),
        imap_user=(e("IMAP_USER") or "").strip() or email,
        imap_password=e("IMAP_PASSWORD") or "",
        imap_folder=e("IMAP_FOLDER") or "INBOX",
        imap_delete_code_mail=_bool(e("IMAP_DELETE_CODE_MAIL")),
        newspaper_title=e("NEWSPAPER_TITLE") or "Die Morgen-Posaune",
        student_name=name or "Du",
        comic_style=(e("COMIC_STYLE") or "classic").strip().lower(),
        next_day_after_hour=int(e("NEXT_DAY_AFTER_HOUR") or 14),
        printer=(e("PRINTER") or "").strip(),
        print_color=_bool(e("PRINT_COLOR"), True),
        event_exclude=e("EVENT_EXCLUDE") or DEFAULT_EVENT_EXCLUDE,
        hide_subjects=[x.strip().lower() for x in (e("HIDE_SUBJECTS") or "").split(",") if x.strip()],
        comic_styles=[x.strip().lower() for x in (e("COMIC_STYLES") or "").split(",") if x.strip()],
        mascot=(e("MASCOT") or "auto").strip().lower(),
        variety=_bool(e("VARIETY"), True),
        edition="morgen" if (e("EDITION") or "abend").strip().lower().startswith("morgen") else "abend",
        openai_api_key=(e("OPENAI_API_KEY") or "").strip(),
        openai_model=(e("OPENAI_MODEL") or "gpt-6-astra,gpt-5.4-mini").strip(),
        ai_content=(e("AI_CONTENT") or "auto").strip().lower(),
        data_dir=PROJECT_ROOT / "data",
        out_dir=PROJECT_ROOT / "out",
    )

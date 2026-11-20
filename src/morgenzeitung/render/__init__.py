"""HTML-Rendering (Jinja2) und PDF-Export (Playwright/Chromium)."""
from __future__ import annotations

import base64
import re
import datetime as dt
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..digest import WEEKDAYS, Digest
from ..variety import Variety
from ..writer import Story

HERE = Path(__file__).parent
THEMES = HERE / "themes"
MASCOTS_DIR = HERE / "mascots"


def available_styles() -> list[str]:
    return sorted(p.stem for p in THEMES.glob("*.css") if p.stem != "base")


FONTS = [  # (Datei, Familie, Gewicht) – lokal eingebettet, damit es offline klappt
    ("Bangers.woff", "Bangers", 400),
    ("ComicNeue-Regular.woff", "Comic Neue", 400),
    ("ComicNeue-Bold.woff", "Comic Neue", 700),
    ("PermanentMarker.woff", "Permanent Marker", 400),
]


def _fonts_css() -> str:
    out = []
    for file, family, weight in FONTS:
        b64 = base64.b64encode((HERE / "fonts" / file).read_bytes()).decode()
        out.append(f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
                   f"src:url(data:font/woff;base64,{b64}) format('woff');}}")
    return "\n".join(out)


def _abbrev(subject: str) -> str:
    s = re.sub(r"\s*\(.*?\)\s*", " ", subject).strip()  # "Sport (Mädchen)" -> "Sport"
    return s if len(s) <= 9 else s[:7].rstrip(" .-") + "."


def mascot_svg(name: str, accessories: list[str]) -> str:
    """Setzt Maskottchen + Accessoires (gemeinsame Ankerpunkte) zu einem SVG zusammen."""
    def part(file: str) -> str:
        f = MASCOTS_DIR / f"{file}.svg"
        return f.read_text() if f.exists() else ""
    body = part(name) or part("owl")
    extras = "".join(part(f"acc_{a}") for a in accessories)
    return (f'<svg viewBox="0 -26 168 196" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="Maskottchen">{body}{extras}</svg>')


def render_html(d: Digest, s: Story, v: Variety) -> str:
    style = v.style
    if style not in available_styles():
        raise ValueError(f"Unbekannter Stil '{style}'. Verfügbar: {', '.join(available_styles())}")
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html", "j2"]))
    tpl = env.get_template("newspaper.html.j2")

    # Woche: Mo–Fr der Woche des Zieltags
    monday = d.day - dt.timedelta(days=d.day.weekday())
    week = [(monday + dt.timedelta(days=i), d.week.get(monday + dt.timedelta(days=i), [])) for i in range(5)]

    # Platz für Hausaufgaben abhängig davon, wie voll die Seite ist
    # Nachrichten links unter den Stundenplan, wenn der Tag nicht zu voll ist
    post_left = len(d.lessons) <= 5
    hw_limit = 7 - len(s.alert_lines) - (3 if d.messages and not post_left else 0)
    hw_limit = max(2, min(6, hw_limit))

    return tpl.render(
        d=d, s=s, v=v, style=style, week=week, hw_limit=hw_limit, post_left=post_left,
        weekday=WEEKDAYS[d.day.weekday()],
        fonts_css=_fonts_css(),
        base_css=(THEMES / "base.css").read_text(),
        theme_css=(THEMES / f"{style}.css").read_text(),
        mascot_svg=mascot_svg(v.mascot, v.accessories),
        short_date=lambda x: f"{WEEKDAYS[x.weekday()][:2]} {x.day}.{x.month}.",
        weekday_short=lambda x: WEEKDAYS[x.weekday()][:2],
        abbrev=_abbrev,
    )


def html_to_pdf(html_path: Path, pdf_path: Path, png_path: Path | None = None) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=2)
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.emulate_media(media="print")
        page.pdf(path=str(pdf_path), format="A4", print_background=True,
                 margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}, prefer_css_page_size=True)
        if png_path:
            page.screenshot(path=str(png_path), full_page=False)
        browser.close()

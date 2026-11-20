from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import traceback

from .config import PROJECT_ROOT, Config, list_profiles, load_config
from .digest import build_digest, pick_target_day, prev_school_day
from .render import available_styles, html_to_pdf, render_html
from .ai_content import daily_content, load_pool
from .variety import Pools, pick_variety
from .writer import write_story


def _demo_raw(day: dt.date) -> dict:
    """Demo-Daten, auf den Zieltag verschoben (Platzhalter __Dn__ = Montag + n Tage)."""
    text = (PROJECT_ROOT / "demo" / "raw.json").read_text()
    monday = day - dt.timedelta(days=day.weekday())
    for n in range(14):
        text = text.replace(f"__D{n}__", (monday + dt.timedelta(days=n)).isoformat())
    return json.loads(text)


def run_one(cfg: Config, args: argparse.Namespace) -> None:
    if args.date:
        day = dt.date.fromisoformat(args.date)
        issued = prev_school_day(day) if cfg.edition == "abend" else day
    else:
        day, issued = pick_target_day(dt.datetime.now(), cfg.next_day_after_hour, cfg.edition)

    if args.demo:
        raw = _demo_raw(day)
        student = "Alex"  # Demo immer mit erfundenem Namen (z. B. für Screenshots)
    else:
        from .sources.dashboard import DashboardClient

        client = DashboardClient(cfg)
        client.ensure_login()
        if args.login_only:
            print(f"✅ Eingeloggt als {cfg.dashboard_email}")
            return
        print(f"📥 Lade Daten für {day} …")
        raw = client.fetch_all(day, raw_dir=cfg.data_dir / "raw" / cfg.profile_slug / day.isoformat())
        student = cfg.student_name

    digest = build_digest(raw, day, student, cfg.event_exclude, cfg.hide_subjects, issued)
    fresh = None if args.no_ai else daily_content(cfg, day)
    pools = Pools(load_pool(cfg), fresh)
    variety = pick_variety(digest, cfg, available_styles(), (args.style or "").lower() or None, pools)
    story = write_story(digest, cfg.newspaper_title, variety)
    style = variety.style

    folder = cfg.profile or cfg.profile_slug
    out = cfg.out_dir / ("demo" if args.demo else folder)
    out.mkdir(parents=True, exist_ok=True)
    base = out / f"zeitung-{day.isoformat()}-{style}"
    html_path, pdf_path, png_path = base.with_suffix(".html"), base.with_suffix(".pdf"), base.with_suffix(".png")
    html_path.write_text(render_html(digest, story, variety))
    html_to_pdf(html_path, pdf_path, png_path)
    print(f"📰 {pdf_path}")
    print(f"   Stil {style}, Kopf {variety.masthead}, {variety.mascot_name}"
          f"{' mit ' + ', '.join(variety.accessories) if variety.accessories else ''}, "
          f"Kästen: {', '.join(b.title for b in variety.boxes)}"
          f" ({'frisch von OpenAI' if pools.is_fresh else 'aus den Listen'})")
    print(f"   {len(digest.lessons)} Stunden, {len(digest.cancelled)} Ausfälle, "
          f"{len(digest.homework)} Hausaufgaben, {len(digest.messages)} Nachrichten")

    if args.open:
        subprocess.run(["open", str(pdf_path)])
    if args.do_print:
        from .outputs.printer import print_pdf

        print(f"🖨️  {print_pdf(cfg, pdf_path)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="zeitung", description="Comic-Morgenzeitung aus dem Schul-Dashboard")
    ap.add_argument("-s", "--student", action="append", metavar="NAME",
                    help="nur dieses Profil (profiles/NAME.env); mehrfach möglich. Standard: alle Profile")
    ap.add_argument("--list", action="store_true", help="Profile auflisten")
    ap.add_argument("--env-file", help="andere Basis-.env")
    ap.add_argument("--date", help="Zieltag YYYY-MM-DD (Standard: heute bzw. nächster Schultag)")
    ap.add_argument("--style", help=f"Comic-Stil, überschreibt COMIC_STYLE ({', '.join(available_styles())})")
    ap.add_argument("--demo", action="store_true", help="Demo-Daten statt Dashboard")
    ap.add_argument("--login-only", action="store_true", help="nur Login prüfen/durchführen")
    ap.add_argument("--print", dest="do_print", action="store_true", help="nach dem Erstellen drucken")
    ap.add_argument("--open", action="store_true", help="PDF danach öffnen")
    ap.add_argument("--no-ai", action="store_true", help="keine OpenAI-Inhalte, nur Listen")
    args = ap.parse_args(argv)

    profiles = list_profiles()
    if args.list:
        for p in profiles:
            c = load_config(args.env_file, p)
            print(f"{p:12} {c.student_name:12} {c.dashboard_email}  Stil: {c.comic_style}")
        if not profiles:
            print("Keine Profile – es wird nur .env benutzt.")
        return 0

    if args.student:
        unknown = [s for s in args.student if s not in profiles]
        if unknown:
            print(f"❌ Unbekannte Profile: {', '.join(unknown)}. Vorhanden: {', '.join(profiles) or '–'}")
            return 2
        selected: list[str | None] = list(args.student)
    else:
        selected = list(profiles) or [None]  # ohne Profile: nur .env

    failed = []
    for p in selected:
        if p:
            print(f"\n===== {p} =====")
        try:
            run_one(load_config(args.env_file, p), args)
        except Exception as exc:  # ein Fehler bei einem Kind soll die anderen nicht stoppen
            failed.append(p or ".env")
            print(f"❌ {p or '.env'}: {exc}")
            if len(selected) == 1:
                traceback.print_exc()
    if failed:
        print(f"\n⚠️  Fehlgeschlagen: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

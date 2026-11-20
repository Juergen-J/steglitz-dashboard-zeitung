from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..config import Config


def print_pdf(cfg: Config, pdf: Path) -> str:
    if not shutil.which("lp"):
        raise RuntimeError("`lp` (CUPS) nicht gefunden")
    cmd = ["lp", "-o", "media=A4", "-o", "fit-to-page"]
    if cfg.printer:
        cmd += ["-d", cfg.printer]
    if not cfg.print_color:
        cmd += ["-o", "ColorModel=Gray", "-o", "print-color-mode=monochrome"]
    cmd.append(str(pdf))
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Druck fehlgeschlagen: {res.stderr.strip()}")
    return res.stdout.strip()

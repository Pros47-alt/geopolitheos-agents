#!/usr/bin/env python3
"""Geopolitheos newsroom.

  python run.py morning [--date YYYY-MM-DD]   run the agent team, stage a draft
  python run.py approve YYYY-MM-DD            human approval: publish the draft

Set GEO_DRY_RUN=1 to run the whole flow offline with canned outputs.
"""

from __future__ import annotations

import argparse
import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agents import chief_of_staff

ROOT = Path(__file__).resolve().parent


def main() -> None:
    settings = tomllib.loads((ROOT / "config/settings.toml").read_text())
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("morning")
    m.add_argument("--date")
    m.add_argument("--out", default=str(ROOT / "out"))
    a = sub.add_parser("approve")
    a.add_argument("date")
    a.add_argument("--out", default=str(ROOT / "out"))
    args = p.parse_args()

    if args.cmd == "morning":
        tz = ZoneInfo(settings["briefing"]["timezone"])
        date = args.date or datetime.now(tz).date().isoformat()
        state = chief_of_staff.run_morning(date, settings, Path(args.out))
        print(f"\nStatus: {state['status']}. Summary: {args.out}/{date}/SUMMARY.md")
        raise SystemExit(1 if state["status"] == "failed" else 0)
    else:
        state = chief_of_staff.approve(args.date, Path(args.out))
        print(f"Published: {state['published']['url']}")


if __name__ == "__main__":
    main()

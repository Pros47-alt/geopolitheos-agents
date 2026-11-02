"""Chief of Staff: runs the morning, hands work between agents, reports up.

Flow:
  News Scout -> Scripture Analyst -> Writer <-> Editor (up to N rounds)
  -> Growth -> Publisher.stage -> summary to the editor-in-chief
Nothing goes live until a human runs `python run.py approve <date>`.
"""

from __future__ import annotations

import json
import os
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import newsroom, publisher

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text()


def _save_state(run_dir: Path, state: dict) -> None:
    (run_dir / "state.json").write_text(json.dumps(state, indent=2))


def _log(state: dict, agent: str, note: str) -> None:
    state["log"].append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "agent": agent, "note": note})
    print(f"[{agent}] {note}", flush=True)


def _format_issues(verdict: dict) -> str:
    return "\n".join(f"- ({i['severity']}) {i['where']}: {i['problem']} -> {i['fix']}"
                     for i in verdict["issues"]) or "- none"


def notify(text: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as exc:  # notification must never break the run
        print(f"[chief_of_staff] Slack notify failed: {exc}")


def run_morning(date: str, settings: dict, out_dir: Path) -> dict:
    run_dir = out_dir / date
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {"date": date, "status": "running", "log": []}
    house_style = _read("prompts/house_style.md")
    scripture_guide = _read("prompts/scripture_guide.md")

    try:
        _log(state, "chief_of_staff", "Morning run started; briefing News Scout.")
        dossier = newsroom.news_scout(date, settings)
        (run_dir / "1_dossier.md").write_text(dossier)
        _log(state, "news_scout", "Dossier ready.")

        notes = newsroom.scripture_analyst(dossier, scripture_guide)
        (run_dir / "2_scripture_notes.md").write_text(notes)
        _log(state, "scripture_analyst", "Scripture notes ready.")

        draft = newsroom.writer(date, dossier, notes, house_style, settings)
        verdict: dict = {}
        rounds = settings["briefing"]["max_editor_rounds"]
        for rnd in range(1, rounds + 2):
            (run_dir / f"3_draft_v{rnd}.md").write_text(draft)
            verdict = newsroom.editor(dossier, draft, house_style)
            (run_dir / f"4_editor_v{rnd}.json").write_text(json.dumps(verdict, indent=2))
            _log(state, "editor", f"Round {rnd}: approved={verdict['approved']}, "
                                  f"{len(verdict['issues'])} issue(s).")
            if verdict["approved"] or rnd > rounds:
                break
            try:
                draft = newsroom.writer(date, dossier, notes, house_style, settings,
                                        previous_draft=draft,
                                        editor_notes=_format_issues(verdict))
            except Exception as exc:
                # Keep the last good draft and the editor's notes for the human.
                _log(state, "writer", f"Revision failed ({exc}); keeping draft v{rnd}.")
                break
            _log(state, "writer", f"Revised draft after round {rnd}.")

        growth_md = ""
        if settings["growth"]["enabled"]:
            growth_md = newsroom.growth(draft, settings)
            (run_dir / "5_growth.md").write_text(growth_md)
            _log(state, "growth", "Social and newsletter drafts ready.")

        state["publish"] = publisher.stage(run_dir, date, draft, settings)
        _log(state, "publisher", f"Staged as draft ({state['publish']['target']}).")

        state["editor"] = verdict
        state["status"] = "awaiting_approval" if verdict.get("approved") else "needs_attention"
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
        (run_dir / "error.txt").write_text(traceback.format_exc())
        _log(state, "chief_of_staff", f"Run failed: {state['error']}")

    summary = _summary(state, run_dir)
    (run_dir / "SUMMARY.md").write_text(summary)
    _save_state(run_dir, state)
    notify(summary)
    return state


def _summary(state: dict, run_dir: Path) -> str:
    date, status = state["date"], state["status"]
    lines = [f"*Geopolitheos: Today for {date}*", f"Status: *{status}*"]
    if status == "failed":
        lines.append(f"Error: {state.get('error')}. See {run_dir}/error.txt")
        return "\n".join(lines)
    v = state.get("editor", {})
    lines.append(f"Editor: {v.get('summary', '')}")
    if v.get("sensitivity_flags"):
        lines.append("Please look personally at:")
        lines += [f"- {f}" for f in v["sensitivity_flags"]]
    open_issues = [i for i in v.get("issues", []) if i["severity"] != "note"]
    if open_issues:
        lines.append("Open issues:")
        lines += [f"- {i['where']}: {i['problem']}" for i in open_issues]
    if state.get("publish", {}).get("wp_preview"):
        lines.append(f"Draft preview: {state['publish']['wp_preview']}")
    lines.append(f"Files: {run_dir}")
    lines.append(f"To publish: `python run.py approve {date}`")
    return "\n".join(lines)


def approve(date: str, out_dir: Path) -> dict:
    run_dir = out_dir / date
    state = json.loads((run_dir / "state.json").read_text())
    if state["status"] not in ("awaiting_approval", "needs_attention"):
        raise SystemExit(f"Cannot approve a run with status '{state['status']}'.")
    result = publisher.publish(run_dir, state)
    state["status"] = "published"
    state["published"] = result
    _log(state, "publisher", f"Published by human approval: {result['url']}")
    _save_state(run_dir, state)
    notify(f"Geopolitheos {date} published: {result['url']}")
    return state

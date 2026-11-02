import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args, tmp):
    env = {**os.environ, "GEO_DRY_RUN": "1"}
    env.pop("SLACK_WEBHOOK_URL", None)
    return subprocess.run([sys.executable, "run.py", *args, "--out", str(tmp)],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def test_morning_then_approve(tmp_path):
    r = run("morning", "--date", "2026-11-02", tmp=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    d = tmp_path / "2026-11-02"
    for f in ["1_dossier.md", "2_scripture_notes.md", "3_draft_v1.md",
              "4_editor_v1.json", "5_growth.md", "briefing.md", "SUMMARY.md"]:
        assert (d / f).exists(), f
    state = json.loads((d / "state.json").read_text())
    assert state["status"] == "awaiting_approval"
    assert "published" not in state  # nothing goes live without approval

    r = run("approve", "2026-11-02", tmp=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads((d / "state.json").read_text())["status"] == "published"


def test_cannot_approve_twice(tmp_path):
    run("morning", "--date", "2026-11-03", tmp=tmp_path)
    run("approve", "2026-11-03", tmp=tmp_path)
    r = run("approve", "2026-11-03", tmp=tmp_path)
    assert r.returncode != 0

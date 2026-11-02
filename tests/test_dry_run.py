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


def test_blocked_domains_parsed_from_api_error():
    from agents.llm import blocked_domains

    err = ("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
           "'message': \"The following domains are not accessible to our user agent: "
           "['apnews.com', 'bbc.com', 'reuters.com']. Read more: https://support.anthropic.com/x\"}}")
    assert blocked_domains(err) == {"apnews.com", "bbc.com", "reuters.com"}
    assert blocked_domains("some other 400") == set()


def test_failed_revision_keeps_last_draft(tmp_path, monkeypatch):
    import tomllib
    from agents import chief_of_staff, llm, newsroom

    monkeypatch.setattr(llm, "DRY_RUN", True)

    settings = tomllib.loads((ROOT / "config/settings.toml").read_text())
    rejected = {**newsroom.DRY["verdict"], "approved": False,
                "issues": [{"severity": "must_fix", "where": "x", "problem": "y", "fix": "z"}]}
    monkeypatch.setattr(newsroom, "editor", lambda *a, **k: rejected)
    real_writer = newsroom.writer

    def writer(*args, **kwargs):
        if kwargs.get("previous_draft"):
            raise RuntimeError("writer: output hit max_tokens")
        return real_writer(*args, **kwargs)

    monkeypatch.setattr(newsroom, "writer", writer)
    state = chief_of_staff.run_morning("2026-11-04", settings, tmp_path)
    assert state["status"] == "needs_attention"
    assert (tmp_path / "2026-11-04" / "briefing.md").exists()

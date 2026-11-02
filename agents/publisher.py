"""Publisher: stages drafts and, only after human approval, publishes.

Targets:
  local      write files to out/<date>/ (always happens)
  wordpress  create a DRAFT post on stage; switch it to publish on approve
"""

from __future__ import annotations

import json
import os
import urllib.request
from base64 import b64encode
from pathlib import Path


def _md_to_html(md: str) -> str:
    try:
        import markdown  # optional dependency

        return markdown.markdown(md)
    except ImportError:
        return "<pre>" + md.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"


def _wp_request(method: str, path: str, body: dict | None = None) -> dict:
    base = os.environ["WP_URL"].rstrip("/")
    token = b64encode(f"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD']}".encode()).decode()
    req = urllib.request.Request(
        f"{base}/wp-json/wp/v2/{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def stage(run_dir: Path, date: str, briefing: str, settings: dict) -> dict:
    """Save the briefing as a draft. Never makes anything public."""
    (run_dir / "briefing.md").write_text(briefing)
    (run_dir / "briefing.html").write_text(_md_to_html(briefing))
    result = {"target": settings["publish"]["target"], "staged": True}

    if settings["publish"]["target"] == "wordpress":
        title = next((l[2:].strip() for l in briefing.splitlines() if l.startswith("# ")), f"Today, {date}")
        post = _wp_request("POST", "posts", {
            "title": title,
            "content": _md_to_html(briefing),
            "status": "draft",
        })
        result.update(wp_post_id=post["id"], wp_preview=post.get("link"))
    return result


def publish(run_dir: Path, state: dict) -> dict:
    """Called only by `run.py approve`. Makes the staged draft public."""
    pub = state.get("publish", {})
    if pub.get("target") == "wordpress" and pub.get("wp_post_id"):
        post = _wp_request("POST", f"posts/{pub['wp_post_id']}", {"status": "publish"})
        return {"published": True, "url": post.get("link")}
    return {"published": True, "url": str(run_dir / "briefing.html")}

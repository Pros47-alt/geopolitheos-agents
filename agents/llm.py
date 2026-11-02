"""Thin wrapper around the Claude API shared by every agent.

Every agent call goes through `ask()`. In dry-run mode no API call is made;
a canned response is returned so the whole pipeline can be tested offline.
"""

from __future__ import annotations

import json
import os
import re

MODEL = os.environ.get("GEO_MODEL", "claude-opus-5-5")
DRY_RUN = os.environ.get("GEO_DRY_RUN") == "1"

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 12}

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic()
    return _client


class AgentRefused(RuntimeError):
    pass


_BLOCKED = re.compile(r"domains are not accessible to our user agent: \[([^\]]*)\]")


def blocked_domains(error_text: str) -> set[str]:
    """Domains named in the API's 'not accessible to our user agent' error."""
    match = _BLOCKED.search(error_text)
    return set(re.findall(r"'([^']+)'", match.group(1))) if match else set()


def _stream(client, agent: str, messages: list, kwargs: dict):
    """Stream one request. Some sites block Anthropic's crawler, and the API
    rejects them in allowed_domains; drop those and retry once."""
    import anthropic

    try:
        with client.beta.messages.stream(messages=messages, **kwargs) as stream:
            return stream.get_final_message()
    except anthropic.BadRequestError as exc:
        blocked = blocked_domains(str(exc))
        tools = kwargs.get("tools") or []
        if not blocked or not tools or "allowed_domains" not in tools[0]:
            raise
        kept = [d for d in tools[0]["allowed_domains"] if d not in blocked]
        if not kept:
            raise
        print(f"[{agent}] Skipping sources that block search: {', '.join(sorted(blocked))}", flush=True)
        tools[0]["allowed_domains"] = kept
        with client.beta.messages.stream(messages=messages, **kwargs) as stream:
            return stream.get_final_message()


def ask(
    agent: str,
    system: str,
    prompt: str,
    *,
    effort: str = "high",
    web_search: bool = False,
    allowed_domains: list[str] | None = None,
    json_schema: dict | None = None,
    max_tokens: int = 64000,
    dry_run_reply: str | dict = "",
):
    """Run one agent turn. Returns text, or a dict when json_schema is given."""
    if DRY_RUN:
        if json_schema is not None:
            return dry_run_reply if isinstance(dry_run_reply, dict) else json.loads(dry_run_reply)
        return dry_run_reply or f"[dry run output from {agent}]"

    client = _get_client()
    tools = []
    if web_search:
        tool = dict(WEB_SEARCH_TOOL)
        if allowed_domains:
            tool["allowed_domains"] = allowed_domains
        tools.append(tool)

    output_config: dict = {"effort": effort}
    if json_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": json_schema}

    messages: list = [{"role": "user", "content": prompt}]
    kwargs = dict(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "adaptive"},
        output_config=output_config,
        # Re-run on a fallback model if a safety classifier declines
        # (geopolitical news can trip false positives).
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if tools:
        kwargs["tools"] = tools

    # Web search turns can pause; send the paused turn back to continue it.
    for _ in range(6):
        response = _stream(client, agent, messages, kwargs)
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    if response.stop_reason == "refusal":
        raise AgentRefused(f"{agent}: request declined ({response.stop_details})")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"{agent}: output hit max_tokens; raise the limit")

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if json_schema is not None:
        return json.loads(text)
    return text

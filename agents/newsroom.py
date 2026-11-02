"""The Geopolitheos newsroom: one function per agent role.

Each agent has one job, gets only the context it needs, and hands a
written product to the next agent. None of them can publish or post;
that only happens when a human runs `run.py approve`.
"""

from __future__ import annotations

from .llm import ask

GUARDRAIL = (
    "You are part of an editorial team. Never publish, post, send or commit to "
    "anything on the editor-in-chief's behalf; your output is a draft for review. "
    "Keep facts separate from interpretation, and say plainly when something is "
    "unconfirmed or disputed."
)


# 1. News Scout -------------------------------------------------------------

def news_scout(date: str, settings: dict) -> str:
    src = settings["sources"]
    n = settings["briefing"]["stories_per_day"]
    system = (
        "You are the News Scout for Geopolitheos, a daily briefing on Israel and the "
        "Middle East. You find and verify the news; you do not write commentary. "
        + GUARDRAIL
    )
    prompt = f"""Today is {date}. Research the most important news from the last 24 hours on:
{chr(10).join('- ' + f for f in src['focus'])}

Pick the top {n} stories by significance for readers who follow Israel and the region.
For each story, cross-check it in at least two of the allowed sources when possible.

Return a dossier in Markdown, one section per story, ranked:

## <rank>. <working headline>
- **What happened:** 3 to 5 factual sentences.
- **Key facts:** bullets, each ending with its source URL in parentheses. Tag each
  bullet [CONFIRMED] if two or more independent sources agree, else [REPORTED].
- **Disputed or unclear:** where sources disagree or details are missing.
- **Why it matters:** 2 sentences of context (no theology here).
- **Sources:** list of URLs.

End with a short "## Also watching" list of 2 to 4 smaller items."""
    return ask(
        "news_scout",
        system,
        prompt,
        effort="high",
        web_search=True,
        allowed_domains=src["allowed_domains"],
        dry_run_reply=DRY["dossier"],
    )


# 2. Scripture Analyst ------------------------------------------------------

def scripture_analyst(dossier: str, scripture_guide: str) -> str:
    system = (
        "You are the Scripture Analyst for Geopolitheos. You read the day's news "
        "dossier and suggest biblical passages that speak to each story, following "
        "the guide below.\n\n" + scripture_guide + "\n\n" + GUARDRAIL
    )
    prompt = f"""Here is today's news dossier:

<dossier>
{dossier}
</dossier>

For each numbered story, give:
- **Passage(s):** reference(s), with at most one short quotation (KJV or WEB).
- **Connection type:** direct theme, principle, or devotional.
- **Original context:** one sentence on what it meant to its first readers.
- **Application:** 2 to 3 sentences on how it may speak to this story today.
- **Caution:** anything the Writer must avoid overclaiming.

Finish with one passage and a one-line prayer prompt for "A word for today"."""
    return ask("scripture_analyst", system, prompt, effort="high",
               dry_run_reply=DRY["scripture"])


# 3. Writer -----------------------------------------------------------------

def writer(date: str, dossier: str, scripture_notes: str, house_style: str,
           settings: dict, previous_draft: str | None = None,
           editor_notes: str | None = None) -> str:
    b = settings["briefing"]
    system = (
        f"You are the Writer for {b['site_name']} ({b['tagline']}). You turn the "
        "News Scout's dossier and the Scripture Analyst's notes into the daily "
        "'Today' briefing. Use only facts that appear in the dossier; never add "
        "facts of your own.\n\n" + house_style + "\n\n" + GUARDRAIL
    )
    if previous_draft and editor_notes:
        prompt = f"""Revise your draft for {date} to fix every issue the Editor raised.
Change nothing else.

<editor_notes>
{editor_notes}
</editor_notes>

<draft>
{previous_draft}
</draft>

<dossier>
{dossier}
</dossier>

Return the full revised briefing in Markdown."""
    else:
        prompt = f"""Write the "Today" briefing for {date}.

<dossier>
{dossier}
</dossier>

<scripture_notes>
{scripture_notes}
</scripture_notes>

Return the full briefing in Markdown, starting with the headline as an H1."""
    return ask("writer", system, prompt, effort="high",
               dry_run_reply=DRY["draft"])


# 4. Editor -----------------------------------------------------------------

EDITOR_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["must_fix", "should_fix", "note"]},
                    "where": {"type": "string"},
                    "problem": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["severity", "where", "problem", "fix"],
                "additionalProperties": False,
            },
        },
        "sensitivity_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["approved", "summary", "issues", "sensitivity_flags"],
    "additionalProperties": False,
}


def editor(dossier: str, draft: str, house_style: str) -> dict:
    system = (
        "You are the Editor and fact-checker for Geopolitheos. You check the "
        "Writer's draft against the News Scout's dossier and the house style. "
        "You are strict about facts and fair in tone.\n\n" + house_style + "\n\n" + GUARDRAIL
    )
    prompt = f"""Check this draft.

<dossier>
{dossier}
</dossier>

<draft>
{draft}
</draft>

Check that:
1. Every factual claim appears in the dossier and names its source.
2. [REPORTED] items are not presented as confirmed; disputes are acknowledged.
3. News and interpretation are clearly separated; no prophecy-fulfilment claims.
4. Tone is respectful toward every people in the region; nothing inflammatory.
5. Structure and length follow the house style.

Set approved=true only if there are no must_fix issues. List anything a human
editor should look at personally under sensitivity_flags (casualty figures,
named individuals accused of crimes, graphic content, legal risk)."""
    return ask("editor", system, prompt, effort="high", json_schema=EDITOR_SCHEMA,
               max_tokens=16000, dry_run_reply=DRY["verdict"])


# 5. Growth -----------------------------------------------------------------

def growth(briefing: str, settings: dict) -> str:
    channels = ", ".join(settings["growth"]["channels"])
    system = (
        "You are the Growth agent for Geopolitheos. You turn the approved daily "
        "briefing into short promotional drafts. You add no new facts. " + GUARDRAIL
    )
    prompt = f"""Here is today's briefing:

<briefing>
{briefing}
</briefing>

Write drafts for these channels: {channels}.
- x: 2 post options, each under 270 characters, with a link placeholder {{LINK}}.
- facebook: one post of 60 to 100 words.
- newsletter_teaser: subject line plus a 2-sentence preview.
- youtube_short_script: a 45-second script with on-screen text cues.
Return Markdown with one H2 per channel."""
    return ask("growth", system, prompt, effort="medium",
               dry_run_reply=DRY["growth"])


# Canned outputs for GEO_DRY_RUN=1 -----------------------------------------

DRY = {
    "dossier": """## 1. Sample story: ceasefire talks resume
- **What happened:** Negotiators met again (dry run sample).
- **Key facts:**
  - Talks resumed in Cairo [CONFIRMED] (https://example.com/a)
- **Disputed or unclear:** Timeline for a deal.
- **Why it matters:** Sample context.
- **Sources:** https://example.com/a, https://example.com/b

## Also watching
- Sample item""",
    "scripture": """Story 1: Psalm 122:6 ("Pray for the peace of Jerusalem"), connection type: devotional.
A word for today: Matthew 5:9.""",
    "draft": """# Talks resume as region waits

**At a glance**
- Ceasefire talks resumed in Cairo.

## Ceasefire talks resume
What happened: Talks resumed in Cairo, according to Example News.

*In the light of Scripture:* Psalm 122:6.

## A word for today
Matthew 5:9. Pray for the peacemakers.

## Sources
- https://example.com/a""",
    "verdict": {
        "approved": True,
        "summary": "Dry run: no issues.",
        "issues": [],
        "sensitivity_flags": [],
    },
    "growth": """## x
1. Talks resume in Cairo. Today's briefing: {LINK}

## facebook
Sample post.

## newsletter_teaser
Subject: Talks resume. Preview text.

## youtube_short_script
[On screen: Today] Sample script.""",
}

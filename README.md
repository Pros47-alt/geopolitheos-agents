# Geopolitheos newsroom agents

An AI "org chart" that drafts the daily **Today** briefing for geopolitheos.com,
"a daily briefing on Israel and the Middle East, read in the light of Scripture."

The structure follows the agent org chart approach Morgan DeBaun describes:
each agent is a named digital employee with one job. A Chief of Staff runs
the day and reports to you. The agents keep facts separate from guesses, and
none of them publishes or posts anything on your behalf.

## The team

| Role | Job | Output |
|---|---|---|
| Chief of Staff | Runs the morning, hands work between agents, sends you one summary | `SUMMARY.md` and a Slack message |
| News Scout | Searches your trusted sources for the last 24 hours and ranks the top stories, tagging each fact CONFIRMED or REPORTED | `1_dossier.md` |
| Scripture Analyst | Pairs each story with passages, labelled direct theme, principle or devotional | `2_scripture_notes.md` |
| Writer | Drafts "Today" in the house voice, using only facts from the dossier | `3_draft_vN.md` |
| Editor | Fact-checks the draft against the dossier, sends it back to the Writer (up to 2 rounds) and flags sensitive items for you | `4_editor_vN.json` |
| Growth | Writes X, Facebook, newsletter and YouTube Short drafts | `5_growth.md` |
| Publisher | Stages the draft locally or as a WordPress draft. It publishes only when you approve | `briefing.md` / `.html` |

```
News Scout -> Scripture Analyst -> Writer <-> Editor -> Growth -> Publisher (draft)
                                                                    |
                                     you: python run.py approve <date>  -> live
```

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...          # or `ant auth login`
python run.py morning                 # today's run (Jerusalem time)
python run.py approve 2026-11-02      # publish after you've read it
```

Offline test with canned outputs: `GEO_DRY_RUN=1 python run.py morning`, or `pytest`.

## Customise without code

- `config/settings.toml`: sources, focus regions, number of stories, channels, publish target
- `prompts/house_style.md`: voice, structure, rules
- `prompts/scripture_guide.md`: theological approach and guardrails

## Schedule

`.github/workflows/morning.yml` runs every day at 03:00 UTC (05:00 or 06:00 in Jerusalem).
Add these repo secrets: `ANTHROPIC_API_KEY`, plus optional `SLACK_WEBHOOK_URL`,
`WP_URL`, `WP_USER` and `WP_APP_PASSWORD`. Each run's files are attached to the workflow run.

## Model

All agents use `claude-opus-5-5` with adaptive thinking (override with `GEO_MODEL`).
The server-side refusal fallback is on, so a false-positive safety decline on hard
news is retried on a fallback model instead of failing the run.

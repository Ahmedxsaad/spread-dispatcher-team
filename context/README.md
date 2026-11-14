# Spread context pack — Junction 2026 (Bahn Express)

Everything an AI coding agent (or a teammate) needs to start building a Spread dispatcher: the official rules and docs, both kits, the live leaderboard picture, and our strategy and research notes.

## How to use it

1. Unzip into the root of your project repo (or next to it).
2. Open the repo in Claude Code (or upload the folder to a Claude project) and say: **"Read CLAUDE.md and start."**
3. Before Claude can play: create the team at spread.bahnexpress.com/join (event code in `06-junction/`), then set `SPREAD_URL=https://spread.bahnexpress.com` and `SPREAD_KEY=<team key>` in the environment. Keep the key out of git.

## What's inside

| Path | Contents |
|---|---|
| `CLAUDE.md` | Start here: mission, targets, setup, how to work, next actions |
| `01-official-docs/` | Verbatim from spread.bahnexpress.com: `RULES.md` (authoritative), `HANDBOOK.md`, `API.md`, `openapi.json`, `llms.txt`, `how-it-works.md`, `judging.md` |
| `02-kits/` | `spread-typescript.tar.gz`, `spread-0.1.0-py3-none-any.whl`, and both unpacked for reading |
| `03-leaderboard/` | Practice rankings for all 8 levels (JSON) + `LEADERBOARD.md` summary; final endpoint status |
| `04-strategy/` | `STRATEGY.md` (levers, architecture, build order, metrics), `TIMELINE.md` (schedule, checklists, final-morning runbook, jury slides), `TECH-PARTNERS.md` (side prizes that fit) |
| `05-research/` | `RESEARCH.md`: papers, libraries and techniques with links |
| `06-junction/` | The Junction challenge page and submission requirements |

## Freshness

Docs and leaderboard were captured on Friday 13 November 2026 in the evening (Helsinki). The rules may be updated during the weekend: re-download `RULES.md` and `HANDBOOK.md` from the site if in doubt, and check the leaderboard live at spread.bahnexpress.com/leaderboard.

# Weekend timeline and checklists (Helsinki time)

Source: `01-official-docs/judging.md` and `HANDBOOK.md`. If Junction's own schedule differs, Junction's schedule is right.

## Schedule

| When | What |
|---|---|
| Fri 19:30 | Hacking starts; first ranking round opens |
| **Fri 23:59** | **Junction preliminary submission** (draft project on hackjunction.app, challenge = Spread) |
| Sat 00:00, 09:00, 12:00, 15:00, 18:00, 21:00 | New ranking rounds (5 secret worlds per level) |
| Sat 12:00 | Junction submissions open |
| **Sat 14:00** | **Test final 1** (random level-8 week from Thursday 00:00, ~19 min; set 13:45, registration pauses 13:45 until it ends) |
| **Sat 20:00** | **Test final 2** (set 19:45) |
| Sun 00:00, 03:00, 06:00 | Last ranking rounds |
| **Sun 07:30** | Final is set; **team registration closes** |
| **Sun 08:00** | **The final** (one secret level-8 week, ~34 min, ends ~08:35) |
| **Sun 10:00** | **Junction final submission closes** (set the project to FINAL; drafts are not reviewed) |
| Sun 10:30–14:00 | Junction review time; the Bahn jury meets the top 10. **Every team member must be at the venue for peer review**, or the team is not eligible for the main prize |
| Sun 14:00 / 15:10 | Final ceremony / challenge winners announced |

## Tonight (Friday)

- [ ] Create the team at spread.bahnexpress.com/join (event code in `06-junction/`), store the key in `.env` (git-ignored).
- [ ] Create the Junction draft submission before 23:59 (Spread / Bahn Express).
- [ ] Run the starter at levels 1, 4, 6, 8; commit the baseline numbers.
- [ ] Build the eval harness (parallel seeds, CSV log, reveal export).
- [ ] First improvement: capacity-aware declining at level 7/8.

## Saturday

- [ ] Morning: fee policy + quote model; play the 09:00/12:00 ranking rounds to compare.
- [ ] Before 14:00: final-mode loop works (stream, rejoin, rate limits). Play **test final 1**; record latency and errors.
- [ ] Afternoon: bundling, notes parser validated on reveals, direct offers.
- [ ] Before 20:00: fix whatever test final 1 exposed. Play **test final 2**.
- [ ] Evening: event detectors, dealer trust; freeze features by ~midnight; only parameter tuning after that.
- [ ] Start the slides skeleton (5–10 slides) and keep filling the ablation table.

## Final-morning runbook (Sunday)

- [ ] 06:30 — machine with a steady connection, ideally a cloud VM near Stockholm (the Spread server is there). Code at the frozen commit; key in env.
- [ ] 07:00 — dry run against a practice world at level 8 to check the build.
- [ ] Before 07:30 — confirm the team is registered (registration closes 07:30).
- [ ] 07:30–07:55 — start the system with the final mode (`--final` in the kit waits for the final when none is set). Run it under a supervisor that restarts it immediately on crash (e.g. a shell loop or systemd), with logs to a file.
- [ ] 08:00–08:35 — one person watches the leaderboard and logs; another is ready to restart. Do not deploy new code mid-final unless the system is broken.
- [ ] 08:40 — note the result; fill the last slide.
- [ ] Before 10:00 — Junction submission set to FINAL with: submission hash (team page), code link, presentation (PDF), demo/video link (Junction requires a pitch video ≤ 2 min).

## Jury presentation (from judging.md)

- 5–10 slides or a short video. Start with the answer: result and big ideas.
- One idea per slide: the idea, why we tried it (what we saw), the effect (margin and on-time with vs without, same weeks).
- Show how the system decides (rule, formula, diagram), not code screenshots.
- Use the challenge's words: dealer, request, gig, fee, typical fee, deadline.
- Say what did not work and what would break the system.
- Jury criteria: **Elegant** (a simple idea doing a lot), **Clear** (we can follow how it decides), **Creative** (an idea they did not expect), **Robust** (does well on unseen weeks — show many-week results; survives restart, slow network, surprises).

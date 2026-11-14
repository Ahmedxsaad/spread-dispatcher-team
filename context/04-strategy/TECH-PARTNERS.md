# Tech challenges (side prizes) that fit a Spread project

On the Junction submission form, one project picks one main challenge (Spread) and can tick any number of **tech challenges**. These are the ones a Spread dispatcher can enter honestly, with what each would mean for us. Prizes are as listed on the Junction platform on 13 Nov 2026.

**Ground rule:** nothing from a partner may put the live final at risk. Anything that calls an external model or service in the live loop needs a short timeout and a deterministic fallback. The final gives ~4.5 real seconds per price request.

## Strong fits

| Tech challenge | Prizes | How it fits Spread |
|---|---|---|
| **Best Use of Gemini API** (Google DeepMind) | 1st €4,000 + $1,000 Google Cloud credits per member · 2nd €2,000 · 3rd €1,000 | Open challenge, judged on meaningful, technical use. Two honest uses: (1) an **offline analyst agent** that reads our reveal CSVs and run log, finds where margin is lost (lanes, fees, misread notes) and proposes the next experiment; (2) a **note reader** for Finnish/Swedish/English dealer notes, scored against the reveal's ground truth, used live only as a fallback with a timeout. Biggest tech prize, but open to every team, so expect a crowd. |
| **Best Use of Gemma** (Google DeepMind) | €1,000 each to 3 teams (no ranking) | A small open model running **on our own machine** to parse notes live, no API dependency during the final. Clear story: "Gemma reads the notes, the parser checks the result against the rules' grammar, accuracy X% on N notes from the reveals." |
| **Best Use of Aiven** | 1st €1,000 · 2nd €750 · 3rd €500 | A managed database for **every practice run, event and result** (hundreds of weeks), with dashboards. It's the evidence base for the jury's ablation slides and lets the whole team query results. Must make a "meaningful difference", so use it for real analysis, not as a token. |
| **Best use of CRACI** | 1st LEGO set per member · 2nd Red Bull · 3rd invite to the CRACI × OpenAI lunch at Slush | Qualifies if the project's CI/CD runs on CRACI (`runs-on: craci` in GitHub Actions). Natural use: **every push runs the eval harness on fixed level-8 seeds** and reports margin and on-time, which is also the jury's "robust over many weeks" evidence. Small prize, ~10 minutes of setup. |
| **Best Use of Vultr** (MLH) | M5Stack mini programmable monitor | Bahn recommends running the final from a machine near **Stockholm**, where the Spread server is. Vultr has a Stockholm region. Low prize, but it solves a real need for the final. |
| **Best Use of Codex** (OpenAI) | 1st $10,000 · 2nd $5,000 · 3rd $2,500 in API credits | Process-based: use Codex meaningfully while building and show how. Only if the team actually codes with Codex. |

## Possible, weaker fits

| Tech challenge | Prizes | Note |
|---|---|---|
| Verda Compute Track | 1st $10,000 cloud credits · 2nd/3rd $2,500 | Wants "something you couldn't build on a laptop". Spread's simulation runs on Bahn's server and is rate-limited, so heavy compute helps little, unless we train a model (e.g. a learned fee or win-probability model over many reveals) on Verda GPUs. |
| Best Use of Nemotron (NVIDIA) | 1x RTX 5080 for each of the two best teams | Reasoning/tool-use model; could power the offline analyst agent instead of Gemini (Verda hosts a Nemotron endpoint). Pick one model family, not both. |
| Best Use of Tiger Data / MongoDB Atlas (MLH) | Stream Deck Mini / M5Stack IoT kit | Alternatives to Aiven for the results/event store. Choose one database. |
| Best use of Modal | see the platform page | Could host the final runner or parallel sweeps; same compute caveat as Verda. |
| Best Use of Entire (MLH) | Mini portable projector | Git forge for agent-human collaboration; fits if the repo and agent sessions live there. |

## No real fit

Solana, ElevenLabs, Cloudinary, Context.dev, Oxylabs, Arduino UNO Q, Atech. Ticking them without real use wastes reviewers' time.

## Suggested set (don't overextend)

1. **Gemma or Gemini** for the note reader (Gemma if we want it local and live; Gemini if we also build the offline analyst agent).
2. **Aiven** as the results database behind the ablation table.
3. **CRACI** for CI that evaluates every commit on fixed seeds.
4. **Vultr** Stockholm VM for the final.

Hackerpack credits that help regardless: Claude ($20/participant), OpenAI Codex ($100), Modal ($100), Verda (€200), Gemini API credits. See the Junction "Developer Tools and Assets" page.

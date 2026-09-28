# Serie A Analytics: project brief

This file tells Claude Code what this project is and how to work on it. Keep it up to date as decisions are made.

## What we are building

A public football analytics website, starting with **Serie A**, with two sections:

1. **Match predictor** (build first): our own model's probabilities for every Serie A match, shown next to the bookmakers' implied probabilities, with a running scoreboard of model vs market accuracy and a simulated final league table.
2. **Transfer valuations** (build later, Phase 3): a model that estimates what players "should" cost, and lists the season's overpays and bargains.

The goal is a portfolio project for finance, trading, data science and consulting internship interviews, and a site that keeps running with little upkeep. It is an **analysis project, not a betting product**: no betting tips, no affiliate links, no "sure bets" language.

## About the owner

- Sofia, a materials science and engineering student at Imperial College London.
- **Strong in:** Python (pandas, NumPy, scikit-learn, Monte Carlo simulation), SQL, BigQuery, Excel, backtesting forecasts.
- **New to:** web development (HTML/CSS/JavaScript, front-end frameworks, deployment), Git and GitHub workflows.
- So: write the Python in a clear, idiomatic way she can own and extend. For the web and Git parts, briefly explain what you're doing and why, as you go, so she learns. Prefer simple, well-known tools over clever ones.

## Data

### Source: football-data.co.uk (free)
- Serie A results and odds per season: `https://www.football-data.co.uk/mmz4281/{season}/I1.csv`, where `{season}` is like `2425` for 2024/25. Serie B is `I2`.
- Upcoming fixtures with odds (all leagues; filter `Div == "I1"`): `https://www.football-data.co.uk/fixtures.csv`
- Useful columns (verify against the actual files on first download, as columns vary by season):
  - `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, `FTR` (full-time goals and result)
  - Pinnacle opening/closing odds: `PSH`, `PSD`, `PSA` and closing `PSCH`, `PSCD`, `PSCA`
  - Market average and Bet365 odds (e.g. `AvgH`/`AvgD`/`AvgA`, `B365H`/`B365D`/`B365A`)
- Credit football-data.co.uk on the site (Methodology/About page).
- Download raw CSVs to `data/raw/` untouched; all cleaning happens in code, never by hand-editing files.
- Build a team-name mapping table (the same club can be spelled differently across seasons and sources).

### Source: openfootball (public domain)
- Official matchday numbers and the full season fixture list: `https://raw.githubusercontent.com/openfootball/football.json/master/{2026-27}/it.1.json` (available from 2014-15). Licence: public domain, "use as you please with no restrictions". Credited on the site.
- Joined to football-data by (season, home_team, away_team), which is unique per season, so postponed matches keep their official matchday. `check_schedule_matches_results` fails the pipeline if a played match is missing from the schedule or the two sources disagree on a score.
- Why: football-data has no matchday numbers, and deriving them from dates fails in 12 of 22 seasons because of postponements.

### Rules
- Respect every site's terms of use. **Do not scrape Transfermarkt** or any site that forbids scraping. If a data source's terms are unclear, stop and ask Sofia.
- No API keys or secrets in the repository. Use environment variables / GitHub Actions secrets if ever needed.

## Models

### 1. Elo rating (baseline)
- One rating per team; home advantage term; goal-difference multiplier on the update; carry ratings across seasons with regression toward the mean (promoted teams start below average).
- Tune K-factor, home advantage and regression on past seasons only.
- Convert rating difference to home/draw/away probabilities (e.g. an ordered logistic model fitted on history).

### 2. Dixon-Coles Poisson model (main)
- Each team gets an attack and a defence strength; plus a home advantage parameter.
- Home goals ~ Poisson(λ), away goals ~ Poisson(μ), with the Dixon-Coles low-score correction (ρ) for 0-0, 1-0, 0-1, 1-1.
- Fit by maximum likelihood (`scipy.optimize`), with **time-decay weighting** (ξ) so recent matches count more. Tune ξ by backtest.
- Output a scoreline probability matrix (0-0 up to at least 8-8), and derive: home/draw/away, over/under 2.5 goals, both teams to score, most likely scorelines.

### 3. Season simulation
- Monte Carlo simulation of all remaining fixtures (at least 10,000 runs) using the Dixon-Coles probabilities.
- Output for each team: expected points, probability of winning the title, Champions League places, European places and relegation.

## Market comparison

- Implied probability = 1 / decimal odds. Bookmaker prices include a margin (overround), so normalise the three probabilities to sum to 1 (proportional method to start; Shin's method as an optional improvement).
- The main benchmark is **Pinnacle closing odds**, widely regarded as the most efficient market price.
- **Decision (Sep 2026):** football-data has no Pinnacle odds after 14 Jan 2026. Backtest against Pinnacle closing where available (2012/13 to Jan 2026). For 2026/27 onwards, use **market-average closing odds** (`avg_close_*`) for that match. Also report how far market-average closing sits from Pinnacle closing in past seasons (2019/20 to 2025/26: about 0.5 points apart on average; log loss 0.9624 vs 0.9617), so readers can see the switch barely matters. Never use a previous season's odds as a benchmark: odds are per match.

## Evaluation (this is the heart of the project)

- **Walk-forward backtest only.** For each matchday, fit models using only matches played before it. No look-ahead, ever. Write a test that fails if any prediction uses data from on or after its match date.
- Metrics: **Ranked Probability Score** (standard for football), log loss, Brier score. Compute the same metrics for the market's implied probabilities.
- Calibration plots (predicted probability vs actual frequency).
- A hypothetical "value" analysis (what if you had backed every match where the model disagreed with the market by more than X?) is allowed as analysis, clearly labelled as hypothetical, with the caveat that the market is hard to beat and past results do not predict future ones.
- Expected, honest result: the model probably will not beat Pinnacle closing odds. That is fine and still interesting. Report results honestly; never tune on the test period to make numbers look better.

## Website

- **Static site** that reads JSON files produced by the Python pipeline.
- **Decision (Sep 2026):** plain HTML/CSS/JavaScript in `site/`, no framework or build step (Node.js isn't installed, and plain files suit a web beginner). Pages are `index.html`, `table.html`, `about.html`; shared code is in `site/js/common.js`, styles in `site/css/style.css`. `python -m pipeline.export` writes `site/data/*.json`, which is committed so Pages can serve it. Revisit Astro only if the site outgrows this (e.g. hundreds of match pages).
- Preview locally with `python3 tools/serve.py` (a no-cache server; plain `http.server` lets browsers reuse stale JS/CSS, and pages opened as plain files can't load the JSON).
- Pages:
  - **Home / This matchday:** fixtures with model vs market probabilities; highlight the biggest disagreements.
  - **Match page:** scoreline heatmap, probabilities, both models, market odds.
  - **Table:** simulated final table (title, Champions League, relegation probabilities).
  - **Model vs market:** season scoreboard (RPS, log loss), calibration chart, history.
  - **Methodology:** plain-English explanation of the models and evaluation, plus data credits.
  - **About:** who built it and why.
- Home page is organised by **matchday**: a swipeable strip of matchday chips ("MD 6 · 10–12 Oct") in the green hero, with ‹ › arrows on desktop; address `#matchday-N`; opens on the next matchday to be played. Sofia disliked the plain dropdown: keep it modern.
- Below the hero, **"The story so far"** talking points computed in the browser from results: biggest shock (lowest probability we gave to what happened), in form (longest unbeaten run), struggling (longest winless run), goal machine (most goals). Sofia asked NOT to show "results we called right" (looks bad). Player stats need a licensed player-data source (Phase 3). Future matchdays show Elo forecasts; market odds appear once football-data publishes them.
- **Design (Sep 2026, chosen by Sofia):** "floodlights" look: near-black header and hero (`--pitch: #0c1210`) with the green-white-red flag stripe on top, a complete pitch drawn faintly on the right of the hero (SVG sized to the hero height, so it is never cut off), bright green (`--neon`) for the selected matchday chip and highlights, rounded pill chips, Barlow / Barlow Condensed fonts, our own football logo. Teams are shown with **mini kit shirts** drawn from each club's traditional home shirt (`site/js/teams.js`: stripes, halves, trim, cross, band). **Never use the official Serie A logo or club crests** (trademarks; the site must not look official); footer states it is not affiliated. Sofia rejected: plain white look, mown-pitch stripes, a cut-off centre circle, a plain dropdown.
- **Keep it simple for casual fans (Sofia, Sep 2026):** the Matches page shows only our prediction (Dixon-Coles, "Our prediction") and a plain-words outlook/verdict (✓ Called it / ✗ Upset / ✗ Not this time). No bookmaker or Elo comparison on the main page: "most people don't care about that". Played matches: the outcome that happened stays bright with a ✓, the others fade.
- **No calculations or formulas on the site** (Sofia, Sep 2026): plain descriptions of each method and numbers only; the maths is in `docs/model-guide.md`.
- Tabs: **Matches** (`index.html`), **Table**, **Market**, **How it works** (`model.html` + `js/guide.js`: plain English. Hit rates with context (Pinnacle 55.2%, goals model 54.1%, Elo 53.4%, always-home 42.2%, guessing 33.3% over 2014/15-2025/26); plain descriptions of the goals model, Elo, the bookmakers and the season simulation; current team ratings table (Elo, attack, defence). Added after Sofia's brother asked for the % correct, more model detail, and what Elo is), **Data lab** (`lab.html`, for data-science readers: per-match bookmakers vs goals model vs Elo with the biggest model-vs-market gap, xG, over 2.5, BTTS; this season's scoreboard (RPS + hit rate); the 12-season backtest (RPS and hit-rate tables); no formulas), **About** (who/why/data). Shared JS: `common.js`, `match.js` (match helpers), `strip.js` (matchday chip strip), `teams.js` (kit colours).
- Mobile-friendly, fast, clean. Available in English (Italian translation is a possible later extra).
- Hosting: **GitHub Pages** on the free tier, deployed by `.github/workflows/deploy.yml` on every push to `main` (tests must pass first). Free Pages needs a **public** repo.

## Distinctive features (chosen by Sofia, Sep 2026)

Brainstormed to make the site stand out. Build in this order:
1. **Prediction record (tamper-evident):** done. `pipeline/ledger.py` appends forecasts for the next round to `predictions/<season>/matchday-NN.json` before kick-off. Append-only: an existing (match_id, model) entry is never changed, and nothing is recorded after kick-off (tests in `tests/test_ledger.py`). Honesty note: local commit timestamps can be set by anyone, so the strong proof is GitHub's own record of when commits were pushed, and it becomes strongest once GitHub Actions commits the forecasts itself (Phase 2). Say this plainly on the site; don't overclaim.
2. **Dixon-Coles** (done) **+ season simulation** (next; prerequisite for 3 and 4).
3. **Serie A as a stock market:** each team's title / top-4 / relegation probability from the simulation, recorded after every matchday and charted over the season like a share price, with big moves annotated. Core of the team pages.
4. **"What if?" simulator:** readers pick results of upcoming matches and the table probabilities recalculate in the browser.

Not chosen for now: luck index, upset hall of fame, Italian translation. Players/transfers stay in Phase 3 (need a licence-compliant source).

## Automation

**Built (Sep 2026):** `.github/workflows/update.yml` runs daily at 06:30 UTC (and via "Run workflow"): tests, download (finished seasons cached), `pipeline.export` (also saves next-round forecasts to `predictions/`), `python -m pipeline.check --since HEAD` (site data sanity + prediction record append-only), then commits only if something besides `summary.json` changed and calls `deploy.yml` (reusable via `workflow_call`; checks out latest `main`). `deploy.yml` also runs the append-only check on every push against `github.event.before`, so nobody can edit a past forecast. Daily (not Tue/Fri) because it's free for public repos and guarantees forecasts are saved before any kick-off. Failure = no commit, no deploy, last good site stays up, GitHub emails the owner. GitHub pauses scheduled workflows after 60 days without repo activity; daily bot commits during the season keep it alive, but check it after the summer break.


- A **GitHub Actions** workflow on a schedule (e.g. Tuesday and Friday mornings, UK time) that downloads new data, refits the models, regenerates JSON, rebuilds the site and deploys it.
- If the pipeline fails, the live site must keep showing the last good data. The workflow should fail loudly (visible in GitHub) rather than publish broken numbers.

## Suggested repository layout

```
.
├── CLAUDE.md
├── README.md
├── pipeline/            # Python package: download, clean, models, evaluation, export
│   ├── data.py
│   ├── elo.py
│   ├── dixon_coles.py
│   ├── simulate.py
│   ├── evaluate.py
│   └── export.py
├── notebooks/           # exploration only; nothing the site depends on
├── tests/               # pytest, including the no-look-ahead test
├── data/
│   ├── raw/             # downloaded CSVs (can be git-ignored and re-downloaded)
│   └── processed/
├── site/                # the website
│   └── data/            # JSON written by the pipeline (committed)
└── .github/workflows/   # scheduled update + deploy
```

## Plan and milestones

| Phase | When | Done when... |
|---|---|---|
| 0. Setup | Early Oct | Repo on GitHub, Python environment, data downloader for Serie A seasons since 2005/06 working, team names cleaned |
| 1. Models + backtest | Oct to Nov | Elo and Dixon-Coles fitted; walk-forward backtest over at least 5 past seasons vs Pinnacle closing; results notebook with RPS, log loss, calibration |
| 1b. First site | Nov | Live site with this matchday's predictions, match pages and methodology page |
| 2. Automation + depth | Dec to Jan | Scheduled weekly updates; season simulation table; model vs market scoreboard; Serie B added if easy |
| 3. Transfer valuations | Feb to Apr | Data source agreed (licence-compliant); valuation model; overpays/bargains pages |
| 4. Polish | May to Jun | Short write-ups of findings, design polish, README that explains the project to a recruiter in 60 seconds |

Work in small steps. At the end of each phase, update this file's "Status" section.

## Conventions

- Python 3.11+, virtual environment (`uv` or `venv`), dependencies pinned in `pyproject.toml` or `requirements.txt`.
- Libraries: pandas, NumPy, SciPy, scikit-learn where useful, pytest. Avoid heavy dependencies unless they clearly earn their place.
- Type hints and short docstrings on public functions. Keep functions small and testable.
- Every model and metric gets at least one test. Run tests before committing.
- Small, descriptive commits. Never commit large data dumps, secrets or generated build output (except the site JSON if the chosen deploy needs it).
- Ask before adding any paid service, account or API.

## Working with collaborators

If other people join the project:
- Nobody pushes directly to `main`. Each change goes on its own branch and becomes a pull request.
- At least one other person reviews a pull request before it is merged.
- Split work by area (e.g. one person on models, one on the site) to avoid editing the same files at once.
- Use GitHub Issues as the to-do list: one issue per task, assigned to one person.

## Status

- [x] Phase 0: Setup. Repo at github.com/sofiaroveda/Serie_A_Analytics (public). `.venv` + pinned `pyproject.toml`, downloader and cleaner (`python -m pipeline.data`), team-name table, 14 tests.
  - Pushing: Sofia pushes with GitHub Desktop; the terminal has no GitHub credentials, so Claude commits and Sofia clicks "Push origin".
  - Data notes (checked Sep 2026): 22 seasons, 8,030 matches, all UTF-8, all passing validation. Pinnacle closing odds cover 2012/13 to 14 Jan 2026 only; football-data stopped publishing Pinnacle odds mid-2025/26, so 2026/27 has none. Market average (`avg_close_*`) and Bet365 closing odds exist from 2019/20. The benchmark for the live season needs a decision (see Market comparison).
  - `fixtures.csv` can have zero Serie A rows between rounds; code handles this.
- [ ] Phase 1: Models + backtest. **Elo done** (`pipeline/elo.py`, `python -m pipeline.elo` re-runs tuning + backtest).
  - Season split (in `pipeline/evaluate.py`): warm-up 2005/06-2007/08, tuning 2008/09-2013/14, test 2014/15-2025/26. Never tune on test seasons.
  - Elo details: World Football Elo goal-difference multiplier; ratings recorded per date before any same-day update; ordered logit (rating gap -> H/D/A) refitted each season on earlier seasons only. Tuned: K=10, home advantage 0 (flat: logit thresholds absorb home advantage), regression 0.3, promoted gap 50.
  - Test result (4,378 matches with Pinnacle closing): RPS base rates 0.2316, Elo 0.1960, Pinnacle 0.1881. Elo loses to Pinnacle in all 12 seasons; captures ~82% of Pinnacle's edge over base rates.
  - `tests/conftest.py::assert_no_lookahead` scrambles results on/after a cut date and checks earlier predictions don't change; reuse it for Dixon-Coles. Verified it catches a deliberately leaky Elo.
  - **Dixon-Coles done** (`pipeline/dixon_coles.py`, `python -m pipeline.dixon_coles` re-runs tuning + backtest). Refitted before every match date on matches in the previous 4 years; analytic gradient (checked against numerical in tests); ridge pull (2.0) towards a prior, weaker for promoted teams. Tuned: half-life 270 days, promoted prior 0.3 (0.15 is equivalent).
  - Test result (same 4,378 matches): RPS base rates 0.2316, Elo 0.1960, **Dixon-Coles 0.1946**, Pinnacle 0.1881. DC beats Elo in 9/12 seasons; captures ~85% of Pinnacle's edge over base rates.
  - Next: results notebook with calibration plots (Phase 1 deliverable), then season simulation.
- [ ] Phase 1b: First site. Brought forward: a version with market + Elo bars per match, table, Model vs market backtest page and About is **live at https://sofiaroveda.github.io/Serie_A_Analytics/** (repo public, Pages source = GitHub Actions). Models get added as they're finished. Data is only refreshed when `python -m pipeline.data && python -m pipeline.export` is run and committed, until Phase 2 automation.
- [ ] Phase 2: Automation + depth. Daily automation built (see Automation). Next: season simulation.
- [ ] Phase 3: Transfer valuations
- [ ] Phase 4: Polish

## To-do list (agreed with Sofia, Sep 2026, in this order)

1. [x] **Automation** (built Sep 2026; first scheduled run to be confirmed). Scheduled GitHub Actions run: download results, refit models, save next-round forecasts to the prediction record, check the data, commit and redeploy. Fail loudly and keep the last good site if anything breaks. Needed before matchday 6 (10 Oct 2026).
2. [x] **Season simulation** (done Sep 2026: `pipeline/simulate.py`, `simulation.json`, Table page "Predicted final table" tab, home talking points Title race / Relegation battle; strength uncertainty 0.10 tuned on 2008/09-2013/14 by Brier score of title/top-4/relegation chances at 4 checkpoints; `python -m pipeline.simulate` re-runs the tuning). Monte Carlo (10,000+ runs) of the remaining fixtures with the goals model: each team's chance of the title, top 4, Europe and relegation; expected points; predicted final table on the Table page.
3. [x] **Stock market / team pages** (done Sep 2026: `market.json` = walk-forward simulation at the start and after each completed matchday (≥8 of 10 played), via `simulate.simulate_as_of`; Market tab `market.html` with Title / Top 4 / Relegation board, movers and sparklines; team pages `team.html?team=X` with tickers, price chart, biggest moves, form, ratings, next matches, results; team names link to team pages). Original spec: Record each team's title / top-4 / relegation chances after every matchday and chart them like a share price, with big moves annotated. A page per team: price chart, form, ratings, upcoming fixtures.
4. [x] **"What if?" simulator** (done Sep 2026: third tab on the Table page, `site/js/whatif.js`; re-simulates 10,000 seasons in the browser with the same method as `pipeline/simulate.py`, seeded RNG with common random numbers so ▲/▼ reflect the picks; phones get a pinned summary bar; browser vs Python agree within Monte Carlo noise: expected points within 0.3, chances within ~1.5 points). Original spec: Readers pick results of upcoming matches; the table chances recalculate in the browser.
5. [x] **Maths page → private model guide** (Sep 2026, Sofia changed her mind: the site keeps only plain descriptions and numbers; formulas, worked example, tuning, results, limitations and interview talking points live in `docs/model-guide.md`. Keep it updated when models or settings change). Original idea: For readers who want to understand the model and the calculations: step-by-step derivations (Poisson, Dixon-Coles likelihood and ρ correction, time weighting, Elo update, ordered logit, odds to probabilities and the bookmaker margin, RPS), a walk-forward testing diagram, how the settings were tuned (with charts), and calibration charts ("when we say 70%, does it happen 70% of the time?"). Include interactive examples where they help. Also covers the Phase 1 calibration deliverable.
6. [ ] **Players.** Use the source with the most data whose terms allow our use (candidates to compare: API-Football, football-data.org, FBref; never Transfermarkt or any site that forbids scraping). Needs Sofia to create the account; API key goes in GitHub Actions secrets, never in the repo. Read the terms before using.
7. [~] **Match pages** (built Sep 2026 with free data only, Sofia's choice: `match.html?id=...` + `js/matchpage.js`; `match_details.json` with generated written report (`pipeline/report.py`: every sentence from a fact, nothing copied), stats (shots, on target, corners, fouls, cards, xG from 2026/27), scorers from openfootball's text file when volunteers add them (`pipeline/scorers.py`, only shown if they add up to the score; none yet for 2026/27), last 5 meetings; previews show top-5 scorelines, xG, over 2.5, BTTS, form. Still missing until a paid source: possession, line-ups, who got the cards). Original spec: Tap a match for: full scoreline grid, all three forecasts, and after full time the stats. Already available from football-data.co.uk: shots, shots on target, corners, fouls, yellow and red cards, and xG (2026/27). Needs the player source (item 6): goal scorers and minutes, who got the cards, possession, line-ups, other key events.
8. [x] **Recruiter README** (done Sep 2026: README.md "in 60 seconds" with live link, results table, pages, stack; the About page carries the same story in plain words. Keep the numbers in both in sync with `backtest.json` if models change).
9. [x] **Table tiebreaks** (done Sep 2026: `pipeline/tiebreak.py` = head-to-head points, head-to-head GD, GD, goals, lots; two-team tie for 1st or across the relegation line = play-off, simulated as a coin toss. Used by the current table, the season simulation / Market, and mirrored in `site/js/whatif.js`).
10. [ ] **Name and link previews (last).** Choose a proper site name first, then add share previews (title, description, image) for WhatsApp / LinkedIn.
11. [ ] Maybe later: Italian version, Serie B, transfer valuations (Phase 3).
12. [x] **Stat predictions** (added Sep 2026 at Sofia's request): corners, yellow cards, shots, shots on target via `pipeline/stats_model.py` (goals-model structure with rho fixed at 0; negative binomial spread for over/under; tuned half-lives 730/365/180/365). Match pages: "Match stats predictions" before kick-off, "Predicted vs actual" after. Backtest vs league average is modest (only shots clearly better): say so honestly. `site/data/stats_backtest.json` is written offline by `python -m pipeline.stats_model`, not by the daily update.

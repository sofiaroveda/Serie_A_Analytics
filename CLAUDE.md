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
- Preview locally with `python3 -m http.server 8000 --directory site` (pages opened as plain files can't load the JSON).
- Pages:
  - **Home / This matchday:** fixtures with model vs market probabilities; highlight the biggest disagreements.
  - **Match page:** scoreline heatmap, probabilities, both models, market odds.
  - **Table:** simulated final table (title, Champions League, relegation probabilities).
  - **Model vs market:** season scoreboard (RPS, log loss), calibration chart, history.
  - **Methodology:** plain-English explanation of the models and evaluation, plus data credits.
  - **About:** who built it and why.
- Mobile-friendly, fast, clean. Available in English (Italian translation is a possible later extra).
- Hosting: **GitHub Pages** on the free tier, deployed by `.github/workflows/deploy.yml` on every push to `main` (tests must pass first). Free Pages needs a **public** repo.

## Automation

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
- [ ] Phase 1: Models + backtest
- [ ] Phase 1b: First site. Brought forward: a market-only version (fixtures, latest results with market probabilities, table, About) is **live at https://sofiaroveda.github.io/Serie_A_Analytics/** (repo public, Pages source = GitHub Actions). Models get added as they're finished. Data is only refreshed when `python -m pipeline.data && python -m pipeline.export` is run and committed, until Phase 2 automation.
- [ ] Phase 2: Automation + depth
- [ ] Phase 3: Transfer valuations
- [ ] Phase 4: Polish

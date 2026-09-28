# Serie A Analytics

**Live site: https://sofiaroveda.github.io/Serie_A_Analytics/**

A forecasting project: my own models put a probability on every Serie A match, the rest of the season is simulated 10,000 times, and everything is tested honestly against the betting market. The site updates itself every morning.

It is an analysis project, not a betting product.

## In 60 seconds

- **Two models built from scratch in Python**: an Elo rating system and a Dixon-Coles goals model (attack and defence strengths, fitted by weighted maximum likelihood with an exact gradient).
- **Tested walk-forward over 12 seasons (4,378 matches)**: every forecast uses only data from before its match, enforced by an automated test. All settings were tuned on earlier seasons.
- **The honest result**: the goals model gets about **85% of the way from no skill to the sharpest bookmaker** (Pinnacle's closing odds), but does not beat it. That is expected: the market knows about injuries and team news.

  | Forecast | Ranked Probability Score (lower is better) | Picks the right result |
  |---|---|---|
  | No skill (base rates) | 0.2316 | 42.2% |
  | Elo | 0.1960 | 53.4% |
  | **Goals model** | **0.1946** | **54.1%** |
  | Pinnacle closing odds | 0.1881 | 55.2% |

- **Season simulation**: 10,000 Monte Carlo seasons give each team's chance of the title, the top 4 and relegation, with the uncertainty level calibrated on past seasons and Serie A's real tie-break rules.
- **Runs itself**: a daily GitHub Actions pipeline downloads results, refits the models, checks the data and republishes the site. Forecasts are saved to an append-only public record before kick-off, and CI blocks any edit to a past prediction.

## What's on the site

| Page | What it shows |
|---|---|
| Matches | Every match by matchday: our prediction, the result and a plain-English verdict; the season's talking points |
| Match pages | A written report generated from the data, goals, stats (shots, xG, corners, cards), past meetings |
| Table | Current standings, the predicted final table, and a **"what if?" simulator** that re-runs 10,000 seasons in the browser |
| Market | Every team's title / top-4 / relegation chances tracked like share prices after each matchday |
| Team pages | Price chart and biggest moves, form, ratings, next matches |
| How it works | The methods in plain English, and how often each one is right |
| Data lab | Our models side by side with the bookmakers, and the full backtest |

## How it's built

- **Python** (pandas, NumPy, SciPy, pytest): data pipeline, models, evaluation, simulation. 85 tests.
- **Website**: plain HTML, CSS and JavaScript, no framework; charts drawn as SVG by hand.
- **Automation and hosting**: GitHub Actions and GitHub Pages, free tier.
- The maths, a worked example, the tuning and all results: [docs/model-guide.md](docs/model-guide.md).

```
pipeline/   download and clean data, Elo, Dixon-Coles, simulation, evaluation, reports, export
tests/      pytest, including the no-look-ahead test
site/       the website; site/data/ is written by the pipeline
predictions/  the append-only prediction record
docs/       the model guide
.github/workflows/  daily update and deploy
```

## Run it yourself

Requires Python 3.11+.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pipeline.data      # download all seasons since 2005/06 and clean them
python -m pipeline.export    # run the models and write the site's data
pytest                       # run the tests
python3 tools/serve.py       # preview the site at http://localhost:8000
```

`python -m pipeline.elo`, `python -m pipeline.dixon_coles` and `python -m pipeline.simulate` re-run the tuning and backtests.

## Data and credits

- Results, odds and match statistics: [football-data.co.uk](https://www.football-data.co.uk/), free of charge.
- Matchday numbers, fixtures and goal scorers: [openfootball](https://github.com/openfootball) (public domain).
- Not affiliated with Lega Serie A or any club. Team colours are shown only to make teams easy to recognise.

## About me

Built by Sofia, a materials science and engineering student at Imperial College London, as a project in forecasting, data analysis and building things that run on their own.

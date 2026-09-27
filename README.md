# Serie A Analytics

Probabilities for every Serie A match from my own models (Elo and Dixon-Coles), compared honestly against bookmaker odds, with a walk-forward backtest and a simulated final table.

This is an analysis project, not a betting product.

## Status

Data pipeline and a first, market-only version of the website are working. The Elo and Dixon-Coles models and the backtest are next.

## Quick start

Requires Python 3.11+.

```bash
python3 -m venv .venv                # create an isolated Python environment
source .venv/bin/activate            # activate it (run this in every new terminal)
pip install -e ".[dev]"              # install this project and its pinned dependencies
python -m pipeline.data              # download all seasons and build data/processed/matches.csv
python -m pipeline.export            # write the website's data files to site/data/
pytest                               # run the tests
```

To view the website locally:

```bash
python3 -m http.server 8000 --directory site   # then open http://localhost:8000
```

## How the models work

See [docs/model-guide.md](docs/model-guide.md) for the formulas, a worked example, how every setting was tuned, and the backtest results.

## Data

Results and odds come from [football-data.co.uk](https://www.football-data.co.uk/), which provides them free of charge. Matchday numbers and the full season fixture list come from [openfootball](https://github.com/openfootball/football.json) (public domain). Thank you to both!

- `data/raw/`: CSV files exactly as downloaded (not committed; re-created by the downloader).
- `data/processed/matches.csv`: one row per match since 2005/06, with standardised team names and odds columns:
  - `pin_*` / `pin_close_*`: Pinnacle pre-match and closing odds (2012/13 to mid-January 2026)
  - `avg_*` / `avg_close_*`: market average odds (closing from 2019/20)
  - `b365_*` / `b365_close_*`: Bet365 odds (closing from 2019/20)
- `data/processed/schedule.csv`: this season's 380 matches with official matchday numbers, played or not.
- `data/team_names.csv`: maps every spelling of a club to one canonical name. The pipeline stops with an error if it meets a name that isn't in this table (e.g. a newly promoted club), so add it there.

## Project layout

```
pipeline/   Python package: download, clean, models, evaluation, export
tests/      pytest tests
data/       raw downloads, processed tables, team-name mapping
notebooks/  exploration only
site/       the website: plain HTML/CSS/JavaScript reading site/data/*.json
```

# Serie A Analytics: model guide

Sofia's reference for how every number on the site is made: the formulas, a worked example, how each setting was chosen, the test results, the limitations, and how to explain it in an interview. The website keeps only plain descriptions and results; the detail lives here.

Numbers are as of 27 September 2026 (2026/27 after matchday 5). The code is the source of truth: file names are given for each part.

---

## 1. The big picture

1. **Data** (`pipeline/data.py`): results and bookmaker odds for every Serie A season since 2005/06 from football-data.co.uk; official matchday numbers and the full fixture list from openfootball.
2. **Two models** give home / draw / away probabilities for every match:
   - **Elo** (`pipeline/elo.py`): one rating per team.
   - **Goals model, Dixon-Coles** (`pipeline/dixon_coles.py`): an attack and a defence rating per team, predicting goals. This is "our prediction" on the site.
3. **Benchmark**: the bookmakers' probabilities (`pipeline/market.py`), mainly Pinnacle's closing odds.
4. **Season simulation** (`pipeline/simulate.py`): plays the rest of the season 10,000 times to get title, top-4, Europe and relegation chances, and the Market history.
5. **Evaluation** (`pipeline/evaluate.py`): walk-forward backtest over 12 seasons, scored with RPS, log loss, Brier score and hit rate.

The golden rule throughout: **every forecast uses only information from before its match date** (walk-forward). A test (`tests/conftest.py::assert_no_lookahead`) scrambles all results from a date onwards and fails if any earlier prediction changes; it was checked against a deliberately cheating model and caught it.

### How the seasons are used

| Seasons | Role |
|---|---|
| 2005/06 to 2007/08 | Warm-up: ratings settle, nothing scored |
| 2008/09 to 2013/14 | Tuning: every setting was chosen here |
| 2014/15 to 2025/26 | Test: never used for tuning (4,378 matches with Pinnacle closing odds) |
| 2026/27 | Live |

---

## 2. From odds to probabilities (`pipeline/market.py`)

Decimal odds $o_H, o_D, o_A$ imply probabilities $1/o_i$, which add up to slightly more than 1: the excess is the bookmaker's margin (overround),

$$\text{margin} = \sum_i \frac{1}{o_i} - 1.$$

We remove it proportionally:

$$p_i = \frac{1/o_i}{\sum_j 1/o_j}.$$

Pinnacle's margin in Serie A is about 2.8%; the market average's about 4.8%. We use **closing odds** (the last prices before kick-off). Pinnacle's odds stop on 14 January 2026, so for 2026/27 the benchmark is the market-average closing price; over 2019/20 to 2025/26 the two differ by about 0.5 percentage points per outcome on average (log loss 0.9624 vs 0.9617), so the switch barely matters.

---

## 3. Elo (`pipeline/elo.py`)

**Expected score** of the home side, given ratings $R_h, R_a$ and home advantage $H$ (in rating points):

$$E_h = \frac{1}{1 + 10^{(R_a - R_h - H)/400}}.$$

A 400-point gap means 10-to-1 odds. After the match, with $S = 1, \tfrac12, 0$ for a home win, draw or loss:

$$\Delta = K \cdot G \cdot (S - E_h), \qquad R_h \leftarrow R_h + \Delta, \quad R_a \leftarrow R_a - \Delta.$$

$G$ is the World Football Elo goal-difference multiplier: 1 for a margin of 0 or 1 goal, 1.5 for 2 goals, $(11 + |\text{gd}|)/8$ for 3 or more.

**Between seasons**, ratings are pulled back towards the mean of 1500,

$$R \leftarrow 1500 + (1 - r)(R - 1500),$$

promoted teams start at $1500 - g$, and all ratings are shifted so the league average stays 1500.

**From ratings to probabilities**: an ordered logistic model on the rating gap $x = (R_h + H - R_a)/400$:

$$P(\text{away}) = \sigma(c_1 - \beta x), \quad P(\text{home}) = 1 - \sigma(c_2 - \beta x), \quad P(\text{draw}) = \sigma(c_2 - \beta x) - \sigma(c_1 - \beta x),$$

with $\sigma$ the logistic function and $c_1 < c_2$. It is fitted by maximum likelihood on all earlier seasons, and refitted at the start of each season (so it never sees the season it predicts).

**No same-day look-ahead**: all matches on a date are rated with the ratings from before that date, then updated.

**Settings** (grid search of 875 combinations, scored by mean RPS on 2008/09 to 2013/14):

| Setting | Value | Meaning |
|---|---|---|
| $K$ | 10 | how fast ratings move |
| $H$ | 0 | home advantage inside the Elo update (the ordered logit already learns home advantage, so this barely matters: RPS differs in the 5th decimal between 0 and 80) |
| $r$ | 0.3 | pull back to the mean between seasons |
| $g$ | 50 | promoted teams' starting gap |

---

## 4. The goals model: Dixon-Coles (`pipeline/dixon_coles.py`)

Home goals $X \sim \text{Poisson}(\lambda)$, away goals $Y \sim \text{Poisson}(\mu)$, with

$$\log \lambda = c + h + a_{\text{home}} + d_{\text{away}}, \qquad \log \mu = c + a_{\text{away}} + d_{\text{home}},$$

where $a$ is attack, $d$ is defence (higher = concedes more), $h$ is home advantage and $c$ the baseline; attacks and defences are each centred to sum to zero.

**Low-score correction** (Dixon and Coles, 1997): the joint probability is multiplied by

$$\tau(x, y) = \begin{cases} 1 - \lambda\mu\rho & (0,0) \\ 1 + \lambda\rho & (0,1) \\ 1 + \mu\rho & (1,0) \\ 1 - \rho & (1,1) \\ 1 & \text{otherwise.} \end{cases}$$

**Fitting**: maximise the time-weighted log-likelihood minus a ridge penalty,

$$\sum_k w_k \Big[\log \tau(x_k, y_k) + x_k \log\lambda_k - \lambda_k + y_k \log\mu_k - \mu_k\Big] \;-\; \kappa \sum_t \Big[(a_t - \bar a_t)^2 + (d_t - \bar d_t)^2\Big],$$

- weight $w_k = 0.5^{\,t_k / 270}$ for a match $t_k$ days old (half-life 270 days), using the previous 4 years of matches;
- $\kappa = 2$ pulls each team towards a prior: 0 for established teams, $\bar a = -0.3$, $\bar d = +0.3$ for promoted teams (who have little Serie A data);
- solved with L-BFGS-B using the exact gradient (checked against a numerical gradient in the tests), $\rho \in [-0.3, 0.3]$;
- refitted **before every match date** in the backtest.

From $\lambda, \mu, \rho$ we build the score matrix $P(X = i, Y = j)$ for $i, j = 0..10$ (renormalised), then sum: home win $= \sum_{i > j}$, draw $= \sum_{i = j}$, away win $= \sum_{i < j}$; over 2.5 goals $= \sum_{i + j \ge 3}$; both teams score $= \sum_{i, j \ge 1}$.

**Settings** (scored by mean RPS on 2008/09 to 2013/14):

| Half-life (days) | 120 | 180 | **270** | 365 | 540 | 730 |
|---|---|---|---|---|---|---|
| Best RPS | 0.20184 | 0.20109 | **0.20078** | 0.20079 | 0.20099 | 0.20120 |

The promoted-team prior barely matters (0.15 and 0.30 differ by 0.000001).

### Worked example: Inter v Parma, 10 October 2026

The current fit (as of the next matchday) has baseline goals $e^c = 1.154$ (an average away side) and home boost $e^h = 1.102$. Written as multipliers ($e^a$, $e^d$): Inter attack 1.93, defence 0.80; Parma attack 0.76, defence 0.97.

$$\lambda = 1.154 \times 1.102 \times 1.93 \times 0.97 \approx 2.38, \qquad \mu = 1.154 \times 0.76 \times 0.80 \approx 0.70$$

(2.39 and 0.70 with the unrounded ratings.)

The score matrix then gives **Inter 74.9%, draw 16.0%, Parma 9.1%**; most likely score 2-0; over 2.5 goals 59.7%; both teams score 45.8%. (Elo for the same match: 80.3% / 13.4% / 6.4%.)

Note the current home boost (1.10) is well below the 1.32 fitted on 2010 to 2012: Serie A home advantage has shrunk in recent seasons, which the time weighting picks up automatically. $\rho$ is currently about 0.

---

## 5. Season simulation (`pipeline/simulate.py`)

For every remaining fixture we take the goals model's $\lambda, \mu$. In each of 10,000 simulated seasons:

1. every team $t$ gets a strength shock $s_t \sim N(0, \sigma^2)$ for the whole simulated season (our uncertainty about how good teams really are, plus form, injuries and transfers);
2. each match is drawn as $X \sim \text{Poisson}(\lambda e^{s_h - s_a})$, $Y \sim \text{Poisson}(\mu e^{s_a - s_h})$ (the $\rho$ correction is left out; it barely changes points);
3. points and goals are added to the real current table, and teams are ranked by Serie A's rules (`pipeline/tiebreak.py`): points; for teams level on points, the mini-league of their matches against each other (head-to-head points, then head-to-head goal difference); then overall goal difference, goals scored and lots. A two-team tie for first place or across the relegation line would be decided by a play-off, which the simulation treats as a coin toss. The same rules order the current table and the "what if?" simulator.

A team's title chance is the share of simulated seasons it finishes first; likewise top 4, top 6 (Europe) and bottom 3.

**Choosing $\sigma$**: each tuning season was stopped after 50, 100, 190 and 280 matches, the rest simulated using only what was known then, and the title / top-4 / relegation chances scored with the Brier score against what happened:

| $\sigma$ | 0.00 | 0.05 | **0.10** | 0.15 | 0.20 | 0.25 | 0.30 |
|---|---|---|---|---|---|---|---|
| Brier | 0.05348 | 0.05323 | **0.05318** | 0.05370 | 0.05450 | 0.05583 | 0.05745 |

Without the shock the simulation is overconfident (Inter 67% for the title after 5 games); with $\sigma = 0.10$ it is 56%.

**"What if?" simulator** (`site/js/whatif.js`): the same simulation re-implemented in the browser (10,000 seasons, about half a second). Picked matches are forced to the chosen result: the score is redrawn from the model until it matches, so a picked home win is usually a plausible scoreline like 1-0 or 2-1. It uses a seeded random number generator with **common random numbers**: every unpicked match gets exactly the same random draws with and without the picks, so the ▲ / ▼ changes come from the picks rather than simulation noise. With no picks it agrees with the Python simulation to within Monte Carlo noise (expected points within 0.3, chances within about 1.5 percentage points).

**Market history** (`pipeline/export.py::market_history`): the same simulation is re-run at the start of the season and after each completed matchday (at least 8 of 10 matches played), each time with only the results known then, so the charts are walk-forward too. The latest point always equals today's predicted table (checked before publishing).

---

## 5b. Corners, cards and shots (`pipeline/stats_model.py`)

The same log-linear team-strength model as the goals model, fitted with $\rho$ fixed at 0 (the low-score correction only makes sense for goals): for each stat, $\log E[\text{home}] = c + h + a_{\text{home}} + d_{\text{away}}$ and $\log E[\text{away}] = c + a_{\text{away}} + d_{\text{home}}$, where $a$ is "won" (e.g. corners won) and $d$ is "conceded". Time-weighted, ridge prior (0.1 for promoted teams), refitted before every match date.

Over / under chances for the match total use a negative binomial with mean $m = \lambda + \mu$ and variance $m + m^2/k$; $k$ is estimated on the tuning seasons by moments, $1/k = (\overline{(y - m)^2} - \bar m)/\overline{m^2}$. Yellow cards vary *less* than Poisson (referees are consistent), so they use a Poisson.

| Stat | Half-life (days) | $k$ | Our mean absolute error (total) | League-average guess | Over / under right |
|---|---|---|---|---|---|
| Corners | 730 | 59.2 | 2.76 | 2.79 | 57.5% (9.5) |
| Yellow cards | 365 | Poisson | 1.60 | 1.63 | 56.5% (4.5) |
| Shots | 180 | 110.5 | 4.40 | 4.72 | 62.9% (24.5) |
| Shots on target | 365 | 64.6 | 2.57 | 2.61 | 58.1% (8.5) |

Test seasons 2014/15 to 2025/26 (about 4,560 matches each); half-lives chosen by Poisson deviance on 2008/09 to 2013/14. **Honest reading**: the models beat the league average on every stat but only slightly, except shots; match stats are mostly noise from game to game, and cards depend on the referee, which the model doesn't know. Re-run with `python -m pipeline.stats_model` (writes `site/data/stats_backtest.json`, which the daily update does not regenerate).

## 6. How accuracy is measured (`pipeline/evaluate.py`)

For a forecast $p = (p_H, p_D, p_A)$ and outcome $o$ (one-hot):

- **Ranked Probability Score** (the standard for football, because outcomes are ordered: predicting a draw when the home side wins is less wrong than predicting an away win):

$$\text{RPS} = \frac{1}{2}\sum_{k=1}^{2}\Big(\sum_{i \le k} p_i - \sum_{i \le k} o_i\Big)^2$$

- **Log loss**: $-\log p_{\text{outcome}}$
- **Brier score**: $\sum_i (p_i - o_i)^2$
- **Hit rate**: how often the outcome rated most likely happened.

All are averaged over matches; lower is better except hit rate. Every forecaster is scored on exactly the same matches.

### Results on the test seasons (2014/15 to 2025/26, 4,378 matches)

| | RPS | Log loss | Hit rate |
|---|---|---|---|
| Base rates (earlier seasons' H/D/A frequencies) | 0.2316 | 1.084 | 42.2% |
| Elo | 0.1960 | 0.979 | 53.4% |
| **Goals model** | **0.1946** | **0.975** | **54.1%** |
| Pinnacle closing | 0.1881 | 0.953 | 55.2% |

- The goals model beats Elo in 9 of 12 seasons; Pinnacle beats both in every season.
- The goals model captures about **85%** of Pinnacle's improvement over base rates: $(0.2316 - 0.1946) / (0.2316 - 0.1881)$.
- Why hit rates top out around 55%: 26% of matches are draws, and a draw is almost never the single most likely outcome.

Per season (RPS):

| Season | Base rates | Elo | Goals model | Pinnacle |
|---|---|---|---|---|
| 2014/15 | 0.2246 | 0.2076 | 0.2050 | 0.2009 |
| 2015/16 | 0.2275 | 0.1987 | 0.1995 | 0.1906 |
| 2016/17 | 0.2320 | 0.1877 | 0.1876 | 0.1805 |
| 2017/18 | 0.2404 | 0.1902 | 0.1845 | 0.1767 |
| 2018/19 | 0.2239 | 0.1892 | 0.1878 | 0.1804 |
| 2019/20 | 0.2415 | 0.2065 | 0.2047 | 0.1968 |
| 2020/21 | 0.2354 | 0.1892 | 0.1886 | 0.1822 |
| 2021/22 | 0.2376 | 0.2029 | 0.1989 | 0.1951 |
| 2022/23 | 0.2303 | 0.2000 | 0.1989 | 0.1951 |
| 2023/24 | 0.2244 | 0.1904 | 0.1914 | 0.1841 |
| 2024/25 | 0.2300 | 0.1909 | 0.1910 | 0.1841 |
| 2025/26 (to 14 Jan) | 0.2306 | 0.2011 | 0.2006 | 0.1933 |

---

## 7. Keeping it honest in production

- **Daily automation** (`.github/workflows/update.yml`): download, refit, save next-round forecasts, check, commit, redeploy.
- **Prediction record** (`pipeline/ledger.py`, `predictions/`): forecasts for the next round are saved before kick-off and never changed. `pipeline/check.py` blocks publishing (and every push) if any past forecast was edited or removed. Caveat: local commit times can be set by anyone; the strong evidence is GitHub's own record of when pushes and automated runs happened.
- **Pre-publish checks**: 380 matches, 10 per matchday, probabilities sum to 1, the table matches the results, the simulation totals add up (one champion, four top-4 places, three relegated), the market's latest point equals the predicted table.

---

## 8. Limitations

- The models only learn from scores: no injuries, suspensions, transfers, coaching changes or rotation. This is the main reason the bookmakers are more accurate.
- The simulation keeps each team's strength fixed within a simulated season (apart from the random shock), treats play-offs as coin tosses, and ignores cup winners' European places.
- The live-season benchmark is the market average, because Pinnacle's odds are no longer published.
- This season's scoreboard covers few matches: its ranking is mostly noise until well into the season.
- Settings were tuned on 2008 to 2014 and not re-tuned since; football has changed (e.g. smaller home advantage), which time weighting only partly absorbs.

---

## 9. How to explain it in an interview

- **One sentence**: "I built two football forecasting models, tested them walk-forward over 12 seasons against the betting market, and publish their predictions daily with a tamper-evident record."
- **The honest headline**: "My best model gets about 85% of the way from no skill to the sharpest bookmaker, but doesn't beat it. That's expected, because the market prices in information my model can't see, like team news."
- **Why RPS**: it respects the order of outcomes, so a near miss scores better than a wild miss; hit rate is intuitive but ignores how confident a forecast was.
- **No look-ahead**: every forecast uses only earlier data; there's an automated test that scrambles future results and fails if any prediction changes, and all settings were tuned on seasons before the test period.
- **Calibrating uncertainty**: the season simulation was overconfident until I added a random strength shock per team, and I chose its size by backtesting title and relegation predictions on past seasons rather than by eye.
- **Engineering**: daily automated pipeline with checks that block publishing on bad data, and an append-only prediction log enforced in CI.

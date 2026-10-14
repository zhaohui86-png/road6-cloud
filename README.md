# road6-cloud

7x24 cloud monitor for ROAD6 watchlist (PC-off capable). Pushes to iPhone via Bark.

- News: Yahoo Finance RSS (7 HK stocks), hard events push instantly, soft events go to daily digest (after HK close).
- Prices: Tencent day-K; buy zones / cross levels per ROAD6 roadmap, one-shot alerts with re-arm.
- Runs every 15 min on GitHub Actions (free for public repos). State (`state.json`) is committed back automatically.

## Setup (one time)

1. Create repo `zhaohui86-png/road6-cloud` (public) on github.com.
2. Add repo secret `BARK_KEY` = your Bark key (Settings -> Secrets and variables -> Actions).
3. Double-click `PUSH_TO_GITHUB.bat` and authorize in browser when prompted.

## Local test

```
BARK_KEY=<key> python cloud_monitor.py
```

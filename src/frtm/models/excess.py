"""Sum model excess over SPF-defined episodes and compare to SPF's published figures."""

from __future__ import annotations

from pathlib import Path

import polars as pl

EXPECTED = Path("data/results/expected_daily.parquet")
EPISODES = Path("data/reference/spf_episodes.csv")
OUT = Path("data/results/episode_comparison.csv")


def main() -> None:
    res = pl.read_parquet(EXPECTED)
    eps = pl.read_csv(EPISODES, try_parse_dates=True)
    rows = []
    for e in eps.iter_rows(named=True):
        win = res.filter(pl.col("date").is_between(e["start"], e["end"]))
        ours = int(win["excess"].sum())
        obs, exp = int(win["deaths"].sum()), int(win["expected"].sum())
        rows.append({**e, "observed": obs, "expected": exp, "our_excess": ours,
                     "our_pct": round(100 * ours / exp, 1), "ratio_to_spf": round(ours / e["spf_excess"], 2)})
    table = pl.DataFrame(rows)
    table.write_csv(OUT)
    pl.Config.set_tbl_width_chars(200)
    print(table.select("episode", "start", "end", "scope", "spf_excess", "our_excess", "our_pct", "ratio_to_spf"))


if __name__ == "__main__":
    main()
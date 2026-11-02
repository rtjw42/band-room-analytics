"""Regenerate the README's Scope and Key results tables from data/.

    .venv/bin/python readme_results.py

The tables sit between `<!-- generated:start -->` and `<!-- generated:end -->`, so a
new snapshot can never leave the README quoting old numbers. refresh.sh runs this after
copying a snapshot in; run it by hand after editing data/ any other way.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "data"
README = ROOT / "README.md"
START, END = "<!-- generated:start -->", "<!-- generated:end -->"
DAY = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}


def num(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def day(d) -> str:
    return pd.Timestamp(d).strftime("%-d %b %Y")


def joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def build() -> str:
    read = lambda name: pd.read_csv(DATA / f"{name}.csv")  # noqa: E731
    kpis = read("01_kpis").set_index("period")
    dist = read("09_distributions")
    wait = read("05_wait_by_window")
    heat = read("03_heatmap")
    weekly = read("02_weekly_demand")
    weekly["week_start"] = pd.to_datetime(weekly["week_start"])
    snapshot = (DATA / "SNAPSHOT").read_text().strip()

    all_time = kpis.loc["All time"]
    d_all = dist[dist["period"] == "All time"].set_index("sort")
    h_all = heat[heat["period"] == "All time"]
    weeks_all = int(h_all["weeks"].iloc[0])
    usage_start = pd.Timestamp(all_time["period_end"]) - pd.Timedelta(days=7 * weeks_all - 1)
    sessions = int(d_all.loc[4, "n"]) if 4 in d_all.index else 0

    complete = weekly[~weekly["partial_week"]]
    recent4 = complete.tail(4)["requests"].mean()
    july = complete.loc[complete["week_start"].dt.month == 7, "requests"].mean()

    evening_share = 100 * h_all.loc[h_all["hour"] >= 19, "booked_hours"].sum() / max(h_all["booked_hours"].sum(), 1)

    h8 = heat[(heat["period"] == "Last 8 weeks") & (heat["hour"] >= 19)].copy()
    weeks8 = int(h8["weeks"].iloc[0])
    by_day = h8.groupby("weekday_name")["booked_hours"].sum() / (weeks8 * 5) * 100
    busiest = by_day.idxmax()
    occ8 = 100 * h8["booked_hours"].sum() / (weeks8 * 35)
    h8["free"] = weeks8 - h8["booked_hours"]
    hardest = h8[h8["free"] == h8["free"].min()]
    hardest_text = (
        f"{len(hardest)} slots tied"
        if len(hardest) > 4
        else joined([f"{DAY[r.weekday_name]} {r.hour:02d}:00" for r in hardest.itertuples()])
    )

    windows = wait[(wait["period"] == "All time") & (wait["bin_order"] == 1)].set_index("submitted_window")
    median = lambda w: f"{num(windows.loc[w, 'window_median_hours'])} h"  # noqa: E731
    pct = lambda a, b: f"{100 * a / b:.1f}% ({a} of {b})" if b else "–"  # noqa: E731

    return "\n".join(
        [
            START,
            "## Scope",
            "",
            "| | |",
            "|---|---|",
            "| Source | Booking database (Postgres, Supabase): `bookings`, `booking_groups` |",
            f"| Requests | Submitted {day(all_time['period_start'])} – {day(all_time['period_end'])} (the last complete week before the snapshot) |",
            f"| Sessions | Held {day(usage_start)} – {day(all_time['period_end'])}; every approved session falls in this range |",
            f"| Snapshot | {day(snapshot)}, SGT |",
            f"| Size | {int(all_time['requests'])} requests; {int(all_time['public_approved'])} public requests with a measurable wait; {sessions} approved sessions |",
            "| Unit | Request (`coalesce(group_id, id)`) unless stated |",
            "| Periods | All time, last 8 weeks, last 4 weeks, selectable in the report |",
            "",
            "## Key results (all time unless stated)",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Requests per week, last 4 complete weeks vs July | {num(recent4)} vs {num(july)} |",
            f"| Hour slots in use falling in 19:00–24:00 | {num(evening_share)}% |",
            f"| Evening occupancy, last 8 weeks (fullest day, {DAY[busiest]} / all days) | {num(by_day[busiest])}% / {num(occ8)}% |",
            f"| Hardest evening slots, last 8 weeks | {hardest_text}: free {int(h8['free'].min())} of {weeks8} weeks |",
            f"| Lead time, median (IQR) | {num(d_all.loc[1, 'median'])} days ({num(d_all.loc[1, 'p25'])}–{num(d_all.loc[1, 'p75'])}) |",
            f"| Approval wait, median / p90 (estimated) | {num(d_all.loc[2, 'median'])} h / {num(d_all.loc[2, 'p90'])} h |",
            f"| Median wait by submission window: daytime / weekend / late night | {median('Weekday daytime')} / {median('Weekend')} / {median('Weekday late night')} |",
            f"| Approved < 24 h before first session (estimated) | {pct(int(all_time['under_24h']), int(all_time['public_approved']))} |",
            f"| Same, among requests made ≥ 48 h ahead | {pct(int(all_time['avoidable_late']), int(all_time['booked_48h_ahead']))} |",
            "",
            "July was the first month of regular use, so part of the rise since then is ramp-up after launch.",
            END,
        ]
    )


def main() -> None:
    text = README.read_text()
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(head + build() + tail)
    print(f"README tables regenerated from the {(DATA / 'SNAPSHOT').read_text().strip()} snapshot.")


if __name__ == "__main__":
    main()

"""Band room booking report.

Descriptive analysis of a band-room booking database: demand, room usage, booking
behaviour, approval latency and data quality. Every figure is computed from the
aggregate CSVs in data/, produced by the SQL in sql/. There is no row-level data in
this repo, so a new snapshot updates every table, chart and sentence together.

Most datasets carry a `period` column (all time, last 8 weeks, last 4 weeks); the
period filter picks rows, it never recomputes from finer data.
"""

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# REPORT_DATA_DIR lets the edge-case tests point the report at synthetic data.
DATA = Path(os.environ.get("REPORT_DATA_DIR") or Path(__file__).parent / "data")
# The refresh script writes the snapshot's SGT date next to the data it describes.
SNAPSHOT = pd.Timestamp((DATA / "SNAPSHOT").read_text().strip()).strftime("%-d %b %Y")
NEXT_RELEASE = "late Nov 2026"
REPO_URL = "https://github.com/rtjw42/band-room-analytics"
PERIODS = ["All time", "Last 8 weeks", "Last 4 weeks"]
REAL_USE_START = pd.Timestamp("2026-07-01")  # earlier days were development and early user testing
SMALL_N = 10

st.set_page_config(page_title="Band room booking report", layout="centered")


# ── Colours ──────────────────────────────────────────────────────────────────
# The band room site's palette: ochre-to-cocoa on cream, ochre-to-sand on warm
# charcoal; never cold blue. Each set passed the colour-blind and contrast checks
# against the site's own surfaces (#f9f6f1 light, #1d1916 dark). Single-series bars
# use the site's button colour (--interactive-bg: warm near-black, cream in dark
# mode); the 4-week mean line takes ochre so it stays distinct from them.
def is_dark() -> bool:
    theme = getattr(st.context, "theme", None)
    return getattr(theme, "type", "light") == "dark"


if is_dark():
    ACCENT, REFERENCE, MUTED, BG, TEXT = "#efeae1", "#b47a3a", "#4a4038", "#1d1916", "#efeae1"
    SHADE = "rgba(180, 122, 58, 0.16)"
    RAMP = ["#6e4c2d", "#93683a", "#b88947", "#d9ae63", "#f2d6a0"]
    HEAT = ["#6e4c2d", "#86603a", "#a07646", "#ba8d52", "#d2a662", "#e6c07c", "#f3d9a6"]
else:
    ACCENT, REFERENCE, MUTED, BG, TEXT = "#251e18", "#b0742f", "#d8cdbd", "#f9f6f1", "#372c25"
    SHADE = "rgba(176, 116, 47, 0.10)"
    RAMP = ["#d6a868", "#bd8648", "#9c6532", "#744523", "#4b2b16"]
    HEAT = ["#d6a868", "#c69154", "#b27a42", "#996335", "#7c4c29", "#5f381e", "#432614"]
FONT = "Outfit, sans-serif"


# ── Data ─────────────────────────────────────────────────────────────────────
@st.cache_data
def read_csv(data_dir: str, name: str) -> pd.DataFrame:
    return pd.read_csv(Path(data_dir) / f"{name}.csv")


def load(name: str) -> pd.DataFrame:
    # The folder is passed explicitly: the cache keys on passed arguments, and a default
    # would let another data folder (the edge-case tests) receive a cached frame.
    return read_csv(str(DATA), name)


kpis = load("01_kpis").set_index("period")
weekly = load("02_weekly_demand")
weekly["week_start"] = pd.to_datetime(weekly["week_start"])
heat_all = load("03_heatmap")
lead_all = load("04_lead_time")
wait_all = load("05_wait_by_window")
mix_all = load("06_request_mix")
sessions_all = load("08_session_length")
dist_all = load("09_distributions")
dq = load("10_data_quality").set_index("sort")
evening_weeks = load("11_evening_by_week")
evening_weeks["week_start"] = pd.to_datetime(evening_weeks["week_start"])
# Requests sent in weeks that ended before real use began, for sessions held after it.
june_requests = int(weekly.loc[weekly["week_start"] + pd.Timedelta(days=6) < REAL_USE_START, "requests"].sum())

DAY = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
DAYS = list(DAY)


def num(x: float) -> str:
    """62.5 -> '62.5', 20.0 -> '20'."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "–"


def date(d) -> str:
    return pd.to_datetime(d).strftime("%-d %b")


def clock(hour: int) -> str:
    """19 -> '7pm', 0 -> '12am', 24 -> 'midnight'."""
    if hour == 24:
        return "midnight"
    return f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"


def when(keys: list[tuple[int, str]]) -> str:
    """(hour, day) pairs in words: 'Wednesday 9pm and 10pm', or 'Monday 7pm and Friday 9pm'."""
    if len({d for _, d in keys}) == 1:
        return f"{DAY[keys[0][1]]} {joined([clock(h) for h, _ in keys])}"
    return joined([f"{DAY[d]} {clock(h)}" for h, d in keys])


def duration(hours: float) -> str:
    """Hours below two days, rounded days from there up."""
    if hours >= 48:
        return f"about {hours / 24:.0f} days"
    return f"{num(hours)} {'hour' if num(hours) == '1' else 'hours'}"


def md_table(rows: list[list], header: list[str]) -> str:
    """Markdown table: text cells wrap instead of truncating, unlike st.dataframe."""
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def open_weeks(week_starts: pd.DatetimeIndex) -> pd.DataFrame:
    """1 for each weekday on or after REAL_USE_START. The first week starts on Monday
    29 Jun, so without this its two days before real use would count as free evenings."""
    return pd.DataFrame(
        {d: (week_starts + pd.Timedelta(days=i) >= REAL_USE_START).astype(int) for i, d in enumerate(DAYS)},
        index=week_starts,
    )


def for_period(period: str) -> dict:
    """Everything the report needs for one period, sliced and derived."""
    k = kpis.loc[period]
    heat = heat_all[heat_all["period"] == period]
    weeks = int(heat["weeks"].iloc[0])
    grid = heat.pivot(index="hour", columns="weekday_name", values="booked_hours")[DAYS]
    evening = grid.loc[19:23]
    usage_start = pd.to_datetime(k["period_end"]) - pd.Timedelta(days=7 * weeks - 1)
    days_open = open_weeks(pd.date_range(usage_start, periods=weeks, freq="7D")).sum()  # weeks per weekday
    first_request = pd.to_datetime(k["period_start"])
    rate_start = max(first_request, REAL_USE_START)
    rate_weeks = ((pd.to_datetime(k["period_end"]) - rate_start).days + 1) / 7
    rate_requests = k["requests"] - (june_requests if first_request < REAL_USE_START else 0)
    occupancy = 100 * evening.sum() / (days_open * 5)  # per weekday
    wait = wait_all[wait_all["period"] == period]
    windows = pd.DataFrame(
        {
            w: {
                "n": int(g["window_requests"].iloc[0]),
                "median": g["window_median_hours"].iloc[0],
                "under_1h": g.loc[g["bin_order"] == 1, "requests"].sum(),
                "over_24h": g.loc[g["bin_order"] >= 4, "requests"].sum(),
            }
            for w, g in wait.groupby("submitted_window")
        }
    ).T.sort_values("median", na_position="last")
    mix = mix_all[mix_all["period"] == period]
    dist = dist_all[dist_all["period"] == period].set_index("sort")
    return {
        "k": k,
        "weeks": weeks,
        "days_open": days_open,
        "evening_hours": int(days_open.sum()) * 5,
        "usage_start": usage_start,
        "weekly_rate": f"{num(rate_requests / rate_weeks)} a week"
        + (f" since {date(REAL_USE_START)}" if first_request < REAL_USE_START else ""),
        "grid": grid,
        "slots": int(grid.values.sum()),
        "evening_share": 100 * evening.values.sum() / grid.values.sum() if grid.values.sum() else 0.0,
        "occupancy": occupancy,
        "occupancy_overall": 100 * evening.values.sum() / (int(days_open.sum()) * 5),
        "lead": lead_all[lead_all["period"] == period],
        "wait": wait,
        "windows": windows,
        "types": mix[mix["dimension"] == "Type"].set_index("label"),
        "outcomes": mix[mix["dimension"] == "Outcome"].set_index("label"),
        "sessions": sessions_all[sessions_all["period"] == period],
        "dist": dist,
    }


def get(df: pd.DataFrame, label: str, col: str) -> int:
    return int(df.loc[label, col]) if label in df.index else 0


# ── Chart helpers ────────────────────────────────────────────────────────────
def figure(label: str) -> None:
    st.markdown(f"**{label}**")


def show(fig: go.Figure, table: pd.DataFrame, height: int, top: int = 40, bottom: int = 8) -> None:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=top, b=bottom),
        font=dict(family=FONT, size=13),
        hoverlabel=dict(font=dict(family=FONT, size=13)),
        dragmode=False,
    )
    # Grow the margins to fit tick labels instead of clipping them.
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with st.expander("Data"):
        st.dataframe(table, hide_index=True, width="stretch")


def single_series_bars(cats, values, hover: str, colors=None, labels=None, horizontal=False) -> go.Figure:
    # Horizontal keeps longer category labels flat on a phone instead of tilting them.
    x, y = (values, cats) if horizontal else (cats, values)
    fig = go.Figure(
        go.Bar(
            x=x,
            y=y,
            orientation="h" if horizontal else "v",
            marker=dict(color=colors or ACCENT, cornerradius=4),
            text=labels,
            textposition="outside",
            cliponaxis=False,
            hovertemplate=hover + "<extra></extra>",
        )
    )
    fig.update_layout(bargap=0.3, showlegend=False, uniformtext=dict(mode="show", minsize=12))
    category_axis, value_axis = (fig.update_yaxes, fig.update_xaxes) if horizontal else (fig.update_xaxes, fig.update_yaxes)
    category_axis(showgrid=False)
    value_axis(rangemode="tozero")
    if horizontal:
        fig.update_yaxes(autorange="reversed")  # first category on top
    return fig


WORDS = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}


def joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# ── All-time figures (the opening summary and closing section ignore the period filter) ──
ALL = for_period(PERIODS[0])
complete = weekly[~weekly["partial_week"]]
recent4 = complete.tail(4)["requests"].mean()
july = complete.loc[complete["week_start"].dt.month == 7, "requests"].mean()
# Rolling 4-week windows smooth a single week's 5 evening slots per day into a readable
# share; each one ends on a Sunday and is one frame of the availability animation.
WINDOW = 4
used = evening_weeks.pivot(index="week_start", columns="weekday_name", values="evening_slots_in_use")[DAYS]
used_roll = used.rolling(WINDOW).sum().dropna()
open_roll = open_weeks(used.index).rolling(WINDOW).sum().dropna()
free_roll = 100 - 100 * used_roll / (open_roll * 5)
labels = [date(w + pd.Timedelta(days=6)) for w in free_roll.index]
first_free = 100 - 100 * used_roll.iloc[0].sum() / (open_roll.iloc[0].sum() * 5)
last_free = 100 - 100 * used_roll.iloc[-1].sum() / (open_roll.iloc[-1].sum() * 5)
last_row = free_roll.iloc[-1]
tightest = [DAY[d] for d, v in last_row.items() if v == last_row.min()]
roomiest = [DAY[d] for d, v in last_row.items() if v == last_row.max()]
many_tight = len(tightest) > 1
now_busiest = f"{joined(tightest)} {'are' if many_tight else 'is'} now the busiest {'evenings' if many_tight else 'evening'}"
ratio = recent4 / july
ka = ALL["k"]
wait_summary = ALL["dist"].loc[2]


def avoidable_clause(late: int, ahead: int) -> str:
    """The late-notice clause, phrased for zero cases instead of '0 of 0'."""
    if not ahead:
        return "no request was made two or more days ahead"
    if not late:
        return f"every one of the {ahead} requests made at least two days ahead was approved at least a day before the session"
    return f"{late} of the {ahead} requests made at least two days ahead were approved less than a day before the session"


def growth(ratio: float) -> str:
    if ratio >= 1.8:
        return "roughly doubled"
    if ratio > 1.15:
        return f"grown by about {100 * (ratio - 1):.0f}%"
    if ratio < 0.87:
        return f"fallen by about {100 * (1 - ratio):.0f}%"
    return "held roughly steady"


# ── Report ───────────────────────────────────────────────────────────────────
st.title("Band room booking report")
st.caption(
    f"This report uses booking data up to {SNAPSHOT}, in Singapore time. Real use began on 1 Jul 2026, so "
    f"sessions before then are left out. Approval times are estimates, and section 2 explains why."
)

free_then = "down from" if last_free < first_free else "up from" if last_free > first_free else "the same as"
with st.container(border=True):
    st.markdown("**In brief**")
    st.markdown(
        f"Real use of the band room began in July, and demand has {growth(ratio)} since then, from "
        f"{num(july)} to {num(recent4)} requests a week"
        + (", though July was the summer break" if ratio > 1.15 else "")
        + f". Most of the room's use falls between 7pm and midnight, and {last_free:.0f}% of those evening hours "
        f"were free in the latest four weeks, {free_then} {first_free:.0f}% in July. {now_busiest}. "
        f"Half of requests are approved within {duration(wait_summary['median'])}, but one in ten waits "
        f"{duration(wait_summary['p90'])} or more, and {avoidable_clause(int(ka['avoidable_late']), int(ka['booked_48h_ahead']))}."
    )
    st.caption("This summary always covers all time.")

period = st.segmented_control("Period", PERIODS, default=PERIODS[0], key="period") or PERIODS[0]
P = ALL if period == PERIODS[0] else for_period(period)
k, d = P["k"], P["dist"]
st.caption(
    f"Showing requests submitted between {date(k['period_start'])} and {date(k['period_end'])}, and "
    f"sessions held between {date(max(P['usage_start'], REAL_USE_START))} and {date(k['period_end'])} ({P['weeks']} weeks). "
    f"The demand chart and sections 5, 8, 9 and 10 do not change with this filter."
)
small = [w for w, s in P["windows"].iterrows() if s["n"] < SMALL_N]

public_n = int(k["public_approved"])
lead_d, wait_d, length_d = (d.loc[i] if i in d.index else None for i in (1, 2, 4))
has_requests, has_sessions = public_n > 0, P["slots"] > 0


def stat(row: pd.Series | None, column: str, unit: str) -> str:
    return f"{num(row[column])} {unit}" if row is not None else "–"

busiest_days = [d for d, v in P["occupancy"].items() if v == P["occupancy"].max()]
quietest_days = [d for d, v in P["occupancy"].items() if v == P["occupancy"].min()]
busiest_names, quietest_names = [DAY[d] for d in busiest_days], [DAY[d] for d in quietest_days]



# 1 ─────────────────────────────────────────────────────────────────────────
st.header("1. Summary")
figure(f"Table 1. Key metrics, {period.lower()}")
wait_at = lambda column: duration(wait_d[column]) if wait_d is not None else "–"
st.markdown(
    md_table(
        [
            ["Requests", int(k["requests"]), P["weekly_rate"]],
            ["Approved requests from the site", public_n, "Sent through the site, then approved"],
            ["Requests entered by admins", int(k["admin_entered"]), "Added already approved"],
            ["Hours in use", P["slots"], f"{P['evening_share']:.0f}% of them between 7pm and midnight"],
            ["Evening hours in use", f"{P['occupancy_overall']:.0f}%", f"Of {P['evening_hours']} evening hours"],
            [
                "Busiest evening",
                joined(busiest_names) if P["occupancy"].max() > 0 else "–",
                f"{P['occupancy'].max():.0f}% of evening hours in use" + (" on each" if len(busiest_days) > 1 else "")
                if P["occupancy"].max() > 0
                else "No evening use",
            ],
            ["Median days ahead", stat(lead_d, "median", "days"), f"{public_n} requests"],
            ["Median approval wait (estimated)", wait_at("median"), f"{public_n} requests"],
            ["90th percentile approval wait (estimated)", wait_at("p90"), f"{public_n} requests"],
            ["Approved under a day before the session (estimated)", pct(k["under_24h"], public_n), f"{int(k['under_24h'])} of {public_n}"],
            ["Made early, approved late (estimated)", pct(k["avoidable_late"], k["booked_48h_ahead"]), f"{int(k['avoidable_late'])} of {int(k['booked_48h_ahead'])} made at least 2 days ahead"],
        ],
        ["Metric", "Value", "Detail"],
    )
)

with st.expander(f"Table 2. Full statistics, {period.lower()}"):
    st.dataframe(
        d[["metric", "unit", "n", "p25", "median", "p75", "p90", "min", "max"]].rename(
            columns={"metric": "Metric", "unit": "Unit", "median": "Median", "min": "Min", "max": "Max"}
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Lead time, wait and notice cover requests made through the site, and session length covers the "
        "approved sessions held in the period."
    )

# 2 ─────────────────────────────────────────────────────────────────────────
st.header("2. Data and definitions")
st.markdown(
    "Real use of the room began on 1 Jul 2026. Before that the site was in development, and the last few "
    "weeks of June were early user testing, so bookings for sessions before 1 Jul are left out of every "
    "figure. The first week starts on 1 Jul, so in All time, Monday and Tuesday have 17 weeks and the other "
    "days have 18. The report draws on two tables. `bookings` has one row per session, with its start and end, "
    "its status (`pending`, `approved` or `rejected`) and when it was created and last updated. "
    "`booking_groups` links the sessions of a multi-date request and records whether the dates were "
    "hand-picked (`custom`) or a weekly repeat (`pattern`). The figures were aggregated in SQL before "
    "export, so no individual booking appears in this report. Section 8 also uses the event log, the "
    "admin chat and the nightly backups to check the approval estimate, and only the results of those "
    "checks are published."
)
st.markdown(
    md_table(
        [
            ["Session", "One row in `bookings`."],
            ["Request", "One submission: `coalesce(group_id, id)`. A multi-date or weekly request counts once."],
            ["Public request", "Approved request with `updated_at > created_at` on every row: submitted, then approved by an admin."],
            ["Admin-entered request", "Approved request with `updated_at = created_at` on any row: inserted already approved. Heuristic: a single-session admin entry edited later counts as public."],
            ["Approval time (estimated)", "`min(updated_at)` across the request's rows: one approval stamps every row, and a later edit moves only the rows it touches. Overstates the wait when a single-session request is edited after approval. Section 8 covers how this was checked."],
            ["Days ahead (lead time)", "First session start minus submission time."],
            ["Notice", "First session start minus approval time (estimated)."],
            ["Made early, approved late (avoidable late notice)", "Notice < 24 h among requests with lead time ≥ 48 h."],
            ["Period", "All time, last 8 weeks or last 4 weeks, ending on the last complete week. Requests fall in the period they were submitted; sessions in the period they were held. Upcoming sessions are excluded."],
            ["Hour in use", "An hour of the week that an approved session covered at least partly. Two sessions sharing an hour count it once."],
            ["Evening hours in use (evening occupancy)", "Evening (19:00–24:00) hours in use ÷ evening hours available in the period, counted from 1 Jul."],
            ["When the request was sent (submission window)", "Weekend: Fri 18:00 – Sun 23:59. Weekday late night: 23:00–07:00. Weekday daytime: the rest."],
            ["Week", "Monday start, SGT."],
        ],
        ["Term", "Definition"],
    )
)

# 3 ─────────────────────────────────────────────────────────────────────────
st.header("3. Demand")
figure(f"Figure 1. Requests per week by date sent ({int(weekly['requests'].sum())} requests)")
fig = go.Figure()
if period != PERIODS[0]:
    fig.add_vrect(
        x0=pd.to_datetime(k["period_start"]) - pd.Timedelta(days=3.5),
        x1=pd.to_datetime(k["period_end"]) - pd.Timedelta(days=3),
        fillcolor=SHADE,
        line_width=0,
        layer="below",
    )
fig.add_bar(
    x=weekly["week_start"],
    y=weekly["requests"],
    name="Requests",
    marker=dict(color=[MUTED if p else ACCENT for p in weekly["partial_week"]], cornerradius=4),
    hovertemplate="Week of %{x|%d %b}: %{y} requests<extra></extra>",
)
rolling = complete.set_index("week_start")["requests"].rolling(4).mean().dropna()
fig.add_scatter(
    x=rolling.index,
    y=rolling.values,
    name="4-week mean",
    mode="lines",
    line=dict(color=REFERENCE, width=2),
    hovertemplate="4-week mean: %{y:.1f}<extra></extra>",
)
# A shape and an annotation, because add_vline cannot label a date axis.
fig.add_shape(type="line", x0=REAL_USE_START, x1=REAL_USE_START, y0=0, y1=1, yref="paper", line=dict(color=TEXT, width=1, dash="dot"))
fig.add_annotation(
    x=REAL_USE_START, y=1, yref="paper", xanchor="left", yanchor="top", xshift=4, showarrow=False, text="Real use begins", font=dict(color=TEXT, size=12)
)
fig.update_layout(bargap=0.25, legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom"))
fig.update_xaxes(showgrid=False, dtick="M1", tickformat="%b")
fig.update_yaxes(rangemode="tozero")
show(
    fig,
    weekly.assign(week_start=weekly["week_start"].dt.date).rename(
        columns={
            "week_start": "Week of",
            "requests": "Requests",
            "sessions": "Sessions",
            "likely_admin_entered": "Admin-entered",
            "partial_week": "Incomplete",
        }
    ),
    320,
)
st.caption(
    f"The chart always shows every week, with the selected period shaded. The {WORDS.get(june_requests, str(june_requests)).lower()} "
    f"requests in June were made during early user testing for sessions held in July, so they count. The grey "
    f"bar is the current week, which is still in progress and left out of the averages."
)
peak = complete.loc[complete["requests"].idxmax()]
total_requests = int(weekly["requests"].sum())
st.markdown(
    (
        f"Requests rose from an average of {num(july)} a week in July to {num(recent4)} a week over the last four "
        f"complete weeks"
        if ratio > 1.15
        else f"Requests averaged {num(july)} a week in July and {num(recent4)} a week over the last four complete weeks"
    )
    + f", and the busiest week was the week of {date(peak['week_start'])}, with {int(peak['requests'])} requests. "
    + (
        "Some of that rise is the room settling in after real use began and some is the start of term, so one "
        "semester cannot show how much of it will last."
        if ratio > 1.15
        else "July falls in the summer break and the recent weeks in term time, so the two are not like for like."
    )
    + f"\n\nCounting the current week, there have been {total_requests} requests, and admins entered "
    f"{int(weekly['likely_admin_entered'].sum())} of them directly. Those count towards demand but not towards "
    f"waits or days ahead, because they never went through approval."
)

# 4 ─────────────────────────────────────────────────────────────────────────
st.header("4. Room usage")
view = st.segmented_control("Heatmap shows", ["Weeks in use", "% of weeks"], default="Weeks in use", key="heat_view") or "Weeks in use"
grid = P["grid"]
share = view == "% of weeks"
z = 100 * grid / P["days_open"] if share else grid
figure(
    f"Figure 2. {'Share of weeks each hour was in use' if share else 'How many weeks each hour was in use'}, "
    f"{period.lower()}" + (f" ({P['weeks']} weeks)" if period == PERIODS[0] else "")
)
steps = len(HEAT) - 1
fig = go.Figure(
    go.Heatmap(
        z=z.where(grid > 0).values,  # never-used slots stay blank
        x=DAYS,
        y=[clock(h) for h in grid.index],
        colorscale=[[i / steps, c] for i, c in enumerate(HEAT)],
        xgap=2,
        ygap=2,
        hoverongaps=False,
        hovertemplate=(
            "%{x} %{y}: in use %{z:.0f}% of weeks<extra></extra>" if share else "%{x} %{y}: %{z} weeks in use<extra></extra>"
        ),
        colorbar=dict(title=dict(text="% of weeks" if share else "Weeks"), thickness=10, len=0.5, ticksuffix="%" if share else ""),
    )
)
fig.update_yaxes(autorange="reversed", showgrid=False)
fig.update_xaxes(side="top", showgrid=False)
show(fig, z.round().reset_index().assign(hour=lambda t: t["hour"].map(clock)).rename(columns={"hour": "Hour"}), 620)
st.caption("Blank squares were never in use. An hour counts as in use if a session covers any part of it.")

figure(f"Figure 3. Share of evening hours in use, by weekday, {period.lower()}")
occ = P["occupancy"]
fig = single_series_bars(
    occ.index,
    occ.values,
    "%{x}: %{y:.0f}% of evening hours in use",
    colors=[ACCENT if day in busiest_days else MUTED for day in occ.index],
    labels=[f"{v:.0f}%" if day in busiest_days + quietest_days else None for day, v in occ.items()],
)
fig.update_yaxes(range=[0, 100], ticksuffix="%")
show(
    fig,
    pd.DataFrame(
        {
            "Day": occ.index,
            "Evening hours in use": grid.loc[19:23].sum().values,
            "Evening hours available": (P["days_open"] * 5).values,
            "Share in use (%)": occ.round().values,
        }
    ),
    300,
)

figure(f"Figure 4. Session length, {period.lower()} ({int(P['sessions']['sessions'].sum())} sessions)")
ses = P["sessions"]
show(
    single_series_bars(ses["bin"], ses["sessions"], "%{y}: %{x} sessions", horizontal=True),
    ses[["bin", "sessions"]].rename(columns={"bin": "Length", "sessions": "Sessions"}),
    260,
)
by_hour = grid.sum(axis=1)
unused = by_hour[by_hour == 0].index.tolist()
if not unused:
    unused_text = ""
elif unused == list(range(unused[0], unused[-1] + 1)):
    unused_text = f", and nothing was booked between {clock(unused[0])} and {clock(unused[-1] + 1)} on any day"
else:
    unused_text = f", and nothing was booked at {joined([clock(h) for h in unused])} on any day"
use_share = (grid / P["days_open"]).stack()
peak = list(use_share[use_share == use_share.max()].index)
in_use = f"in use in {int(grid.loc[peak[0]])} of the {int(P['days_open'][peak[0][1]])} weeks"
if len(peak) == 1:
    peak_text = f"The busiest time was {when(peak)}, {in_use}."
elif len(peak) <= 3:
    peak_text = f"The busiest times were {when(peak)}, each {in_use}."
else:
    peak_text = f"No single time stood out, with {WORDS.get(len(peak), str(len(peak))).lower()} times tied as the busiest, each {in_use}."
if not has_sessions:
    st.markdown("No sessions were held in this period.")
else:
    if occ.max() == occ.min():
        fullest_text = f"Every evening was equally full at {occ.max():.0f}%."
    else:
        many_full = len(busiest_names) > 1
        fullest_text = (
            f"{joined(busiest_names)} {'were the fullest evenings' if many_full else 'was the fullest evening'} at "
            f"{occ.max():.0f}% and {joined(quietest_names)} the quietest at {occ.min():.0f}%"
        )
        if set(busiest_names) & set(tightest):
            fullest_text += "."
        else:
            fullest_text += (
                f", though {joined(tightest)} {'were' if many_tight else 'was'} the fullest in the latest four weeks."
            )
    st.markdown(
        f"Most of the room's use, {P['evening_share']:.0f}%, falls between 7pm and midnight{unused_text}. {peak_text}\n\n"
        f"Across the week, {P['occupancy_overall']:.0f}% of evening hours were in use. {fullest_text} "
        f"Half of sessions ran {duration(length_d['median'])} or less, and the longest ran {duration(length_d['max'])}."
    )

# 5 ─────────────────────────────────────────────────────────────────────────
st.header("5. Room availability")
st.markdown("An evening hour, between 7pm and midnight, counts as free if nothing is booked during any part of it.")

# This whole section ignores the period filter. The table answers "when is the room free
# now?", and All time would hide the pressure behind the quiet early weeks.
ra = for_period("Last 8 weeks")
evening_free = (ra["days_open"] - ra["grid"]).loc[19:23]  # weeks each evening hour was free
FREE_USUALLY, FREE_RARELY = 6, 2  # weeks out of the last 8


def time_ranges(hours: list[int]) -> str:
    """Evening hours as plain time ranges, so [19, 20, 22] reads '7–9pm, 10–11pm'."""
    if not hours:
        return "–"
    if len(hours) == len(evening_free):
        return "All evening"
    runs: list[list[int]] = []
    for h in hours:
        if runs and runs[-1][1] == h:
            runs[-1][1] = h + 1
        else:
            runs.append([h, h + 1])
    return ", ".join(f"{clock(a)} to midnight" if b == 24 else f"{a - 12}–{clock(b)}" for a, b in runs)


def free_times(day: str) -> list[str]:
    free = evening_free[day]
    groups = [free >= FREE_USUALLY, (free > FREE_RARELY) & (free < FREE_USUALLY), free <= FREE_RARELY]
    return [day, *(time_ranges(free[g].index.tolist()) for g in groups)]


figure("Table 3. When the room is free, last 8 weeks")
st.markdown(md_table([free_times(day) for day in DAYS], ["Day", "Usually free", "Sometimes free", "Rarely free"]))
st.caption(
    f"Usually free means free in at least {FREE_USUALLY} of the {ra['weeks']} weeks, rarely free means "
    f"{FREE_RARELY} or fewer, and sometimes free is anything in between."
)

free_share = (evening_free / ra["days_open"]).stack()
hardest = list(free_share[free_share == free_share.min()].index)
day_free = 100 * evening_free.sum() / (ra["days_open"] * 5)
easiest = [DAY[day] for day, v in day_free.items() if v == day_free.max()]
one, many_easy = len(hardest) == 1, len(easiest) > 1
hard_free = "booked every week" if free_share.min() == 0 else f"free in only {int(evening_free.loc[hardest[0]])} of the {ra['weeks']} weeks"
if len(hardest) > 4:
    hardest_text = f"{len(hardest)} evening times tied as the hardest to book, each {hard_free}"
else:
    hardest_text = f"{when(hardest)} {'was the hardest time' if one else 'were the hardest times'} to book, {'' if one else 'each '}{hard_free}"
if not ra["slots"]:
    st.markdown("No evening hour was booked over the last 8 weeks.")
else:
    st.markdown(
        f"Over the last 8 weeks, {hardest_text}, and {joined(easiest)} "
        f"{'were the easiest evenings' if many_easy else 'was the easiest evening'}, with {day_free.max():.0f}% of "
        f"{'their' if many_easy else 'its'} hours free."
    )


def availability_bars(row: pd.Series) -> go.Bar:
    low = row.min()
    return go.Bar(
        x=DAYS,
        y=row.values,
        marker=dict(color=[ACCENT if v == low else MUTED for v in row.values], cornerradius=4),
        text=[f"{v:.0f}%" if v == low else "" for v in row.values],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{x}: %{y:.0f}% of evening hours free<extra></extra>",
    )


figure("Figure 5. Share of evening hours free, by weekday, four weeks at a time")
fig = go.Figure(
    data=[availability_bars(free_roll.iloc[-1])],
    frames=[go.Frame(data=[availability_bars(row)], name=lbl) for lbl, (_, row) in zip(labels, free_roll.iterrows(), strict=True)],
)
step = dict(frame=dict(duration=700, redraw=True), transition=dict(duration=450, easing="cubic-in-out"), mode="immediate")
fig.update_layout(
    showlegend=False,
    uniformtext=dict(mode="show", minsize=12),
    # Opens on the latest window and never autoplays, so it reads correctly as a still.
    updatemenus=[
        dict(
            type="buttons",
            direction="left",
            showactive=False,
            x=0,
            y=1.02,
            xanchor="left",
            yanchor="bottom",
            bgcolor=BG,
            bordercolor=MUTED,
            font=dict(family=FONT, color=TEXT, size=13),
            buttons=[
                dict(label="▶  Play", method="animate", args=[None, dict(step, fromcurrent=False)]),
                dict(label="❚❚  Pause", method="animate", args=[[None], dict(frame=dict(duration=0, redraw=False), transition=dict(duration=0), mode="immediate")]),
            ],
        )
    ],
    sliders=[
        dict(
            active=len(labels) - 1,
            x=0,
            len=1,
            y=-0.06,
            yanchor="top",
            pad=dict(t=8, b=0),
            ticklen=0,
            bgcolor=MUTED,
            activebgcolor=ACCENT,
            bordercolor=MUTED,
            font=dict(color="rgba(0,0,0,0)"),  # one tick label per week would crowd a phone
            currentvalue=dict(prefix="Four weeks to ", font=dict(family=FONT, color=TEXT, size=13), xanchor="left"),
            steps=[
                dict(method="animate", label=lbl, args=[[lbl], dict(mode="immediate", frame=dict(duration=300, redraw=True), transition=dict(duration=300))])
                for lbl in labels
            ],
        )
    ],
)
fig.update_xaxes(showgrid=False)
fig.update_yaxes(range=[0, 105], ticksuffix="%")
show(
    fig,
    free_roll.round().assign(window_end=labels).reset_index(drop=True)[["window_end", *DAYS]].rename(columns={"window_end": "Four weeks to"}),
    420,
    top=56,
    bottom=96,
)
st.caption(
    "Each bar covers four weeks, so one unusual week does not swing it, and the dark bar marks the day with "
    "the fewest free hours. Press Play to step through the whole history."
)

went, change = ("fell", "drop") if last_free < first_free else ("rose", "rise") if last_free > first_free else ("went", "change")
st.markdown(
    f"The share of free evening hours {went} from {first_free:.0f}% in the four weeks to {labels[0]} to "
    f"{last_free:.0f}% in the four weeks to {labels[-1]}, and part of that {change} is the move from the summer "
    f"break into term time. {now_busiest}, with {last_row.min():.0f}% of {'their' if many_tight else 'its'} hours free."
)

# 6 ─────────────────────────────────────────────────────────────────────────
st.header("6. Booking behaviour")
lead = P["lead"]
figure(f"Figure 6. Days ahead, requests from the site, {period.lower()} ({public_n} requests)")
show(
    single_series_bars(lead["bin"], lead["requests"], "%{y}: %{x} requests", horizontal=True),
    lead[["bin", "requests"]].rename(columns={"bin": "Days ahead", "requests": "Requests"}),
    280,
)
types = P["types"]
approved_n = int(types["requests"].sum())
figure(f"Table 4. Request type, approved requests, {period.lower()}")
st.markdown(
    md_table(
        [[label.capitalize(), int(r["requests"]), pct(r["requests"], approved_n), int(r["sessions"])] for label, r in types.iterrows()],
        ["Type", "Requests", "Share", "Sessions"],
    )
)
st.caption(
    "Custom requests cover hand-picked dates and pattern requests repeat weekly. This table includes "
    "sessions still to come, so its total can be higher than Figure 4's."
)
under_day = int(lead.loc[lead["bin_order"] == 1, "requests"].sum())
multi = types.drop(index="one-off", errors="ignore")
multi_n = int(multi["requests"].sum())
multi_text = (
    f"Most requests are for a single session, and only {multi_n} of {approved_n} ({pct(multi_n, approved_n)}) "
    f"covered several dates."
    if multi_n
    else "Every approved request in this period was for a single session."
    if approved_n
    else ""
)
if not has_requests:
    st.markdown("No requests were made through the site in this period." + (f"\n\n{multi_text}" if multi_text else ""))
else:
    st.markdown(
        f"Half of requests came within {num(lead_d['median'])} days of their first session, and only one in ten "
        f"came more than {num(lead_d['p90'])} days ahead. Of the {public_n} requests, {under_day} "
        f"({pct(under_day, public_n)}) came less than a day before.\n\n"
        + multi_text
    )

# 7 ─────────────────────────────────────────────────────────────────────────
st.header("7. Approval process")
windows, wait = P["windows"], P["wait"]
figure(f"Figure 7. Estimated approval wait by when the request was sent, {period.lower()} ({public_n} requests)")
order = windows.index.tolist()
fig = go.Figure()
bins = wait[["bin_order", "wait_bin"]].drop_duplicates().sort_values("bin_order")
for color, (_, b) in zip(RAMP, bins.iterrows(), strict=True):
    rows = wait[wait["wait_bin"] == b.wait_bin].set_index("submitted_window").loc[order]
    fig.add_bar(
        y=order,
        x=100 * rows["requests"] / rows["window_requests"].where(rows["window_requests"] > 0),
        customdata=rows["requests"],
        name=b.wait_bin,
        orientation="h",
        marker=dict(color=color, line=dict(color=BG, width=2)),
        hovertemplate=f"%{{y}}, {b.wait_bin}: %{{x:.0f}}% (%{{customdata}} requests)<extra></extra>",
    )
# Window names sit above their bars rather than beside them, so the bars keep the full
# width on a phone.
for w, s in windows.iterrows():
    fig.add_annotation(
        x=0, y=w, xanchor="left", yanchor="bottom", yshift=24, showarrow=False, text=f"<b>{w}</b>  {int(s['n'])} requests"
    )
fig.update_layout(barmode="stack", bargap=0.6, legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom", traceorder="normal"))
fig.update_xaxes(range=[0, 100], ticksuffix="%", showgrid=False)
fig.update_yaxes(autorange="reversed", showticklabels=False)
show(
    fig,
    wait[["submitted_window", "wait_bin", "requests", "window_requests"]].rename(
        columns={"submitted_window": "Sent", "wait_bin": "Wait", "requests": "Requests", "window_requests": "Requests in group"}
    ),
    340,
    top=64,
)

figure(f"Table 5. Estimated approval wait by when the request was sent, {period.lower()}")
st.markdown(
    md_table(
        [
            [w, int(s["n"]), duration(s["median"]) if pd.notna(s["median"]) else "–", pct(s["under_1h"], s["n"]), pct(s["over_24h"], s["n"])]
            for w, s in windows.iterrows()
        ],
        ["Sent", "Requests", "Median wait", "Within 1 hour", "Over 24 hours"],
    )
)
if small:
    names = joined([w.lower() for w in small])
    st.caption(
        f"Fewer than {SMALL_N} requests fall in the {names} {'group' if len(small) == 1 else 'groups'}, "
        f"so treat {'its' if len(small) == 1 else 'their'} figures as a rough guide."
    )
answered = windows[windows["n"] > 0]  # an empty window has no median to compare
SENT = {
    "Weekday daytime": "requests sent during the weekday daytime",
    "Weekday late night": "requests sent late on weeknights",
    "Weekend": "requests sent at the weekend",
}
after = int(k["approved_after_start"])
after_text = (
    f"\n\n{'One request appears' if after == 1 else f'{WORDS.get(after, str(after))} requests appear'} to have been "
    f"approved after {'its' if after == 1 else 'their'} first session had started, which section 8 looks at."
    if after
    else ""
)
late, ahead, late_ok = int(k["under_24h"]), int(k["booked_48h_ahead"]), int(k["avoidable_late"])
if not has_requests:
    st.markdown("No requests were made through the site in this period, so there are no waits to report.")
else:
    if len(answered) >= 2:
        slowest, fastest = answered["median"].idxmax(), answered["median"].idxmin()
        by_window = (
            f" {SENT[slowest].capitalize()} waited longest, and half of them waited "
            f"{duration(answered.loc[slowest, 'median'])} or more, against {duration(answered.loc[fastest, 'median'])} "
            f"for {SENT[fastest]}."
        )
    else:
        by_window = ""
    if not late:
        notice = f"None of the {public_n} requests was approved less than a day before its first session."
    else:
        notice = (
            f"Long waits matter most when the session is close. Of {public_n} requests, {late} "
            f"({pct(late, public_n)}) were approved less than a day before their first session, and "
            f"{late - late_ok} of those were submitted less than two days ahead, so there was little time to "
            f"answer faster."
        )
    if not ahead:
        planned = " No request in this period was submitted two or more days ahead."
    elif not late_ok:
        planned = f" Every one of the {ahead} requests submitted at least two days ahead got at least a day's notice."
    else:
        planned = (
            f" The other {late_ok}, out of {ahead} requests submitted at least two days ahead, "
            f"{'is the case' if late_ok == 1 else 'are the cases'} a faster process could prevent."
        )
    st.markdown(
        f"Half of requests were approved within {duration(wait_d['median'])} and three in four within "
        f"{duration(wait_d['p75'])}, but one in ten waited {duration(wait_d['p90'])} or more, and the longest "
        f"took {duration(wait_d['max'])}.{by_window}\n\n{notice}{planned}"
        + after_text
    )

# 8 ─────────────────────────────────────────────────────────────────────────
st.header("8. Data quality and instrumentation")
figure("Table 6. Data-quality checks, all records")
impact = {
    1: ("Excluded from wait and lead-time metrics; identified by a heuristic.", "Exact from 28 Oct (event log)"),
    2: ("Inflate the wait and notice tails. The nightly backups show no later edit to any of them, so these look like approvals given after the session began.", "Checked against backups"),
    3: ("Part of an admin-entered request, so excluded from lead-time figures.", "No effect"),
    4: ("Weight the heatmap; may include entry errors.", "Unverified"),
    5: ("22:00–06:00 sessions in July; possibly AM/PM entry errors.", "Unverified"),
    6: ("Development and early user testing, so these are in no figure in this report.", "Excluded"),
    7: (
        "None pending at snapshot time." if dq.loc[7, "affected"] == 0
        else "Awaiting a decision at snapshot time; not part of any period figure.",
        "–",
    ),
}
st.markdown(
    md_table(
        [
            [r["check_name"], f"{int(r['affected'])} {r['unit'].rstrip('s') if r['affected'] == 1 else r['unit']}", *impact.get(i, ("", ""))]
            for i, r in dq.iterrows()
        ],
        ["Check", "Affected", "Impact", "Status"],
    )
)

st.caption(
    "These checks count every record up to the snapshot, including the current, unfinished week, so a count "
    "can differ slightly from the period figures above."
)

figure("Table 7. Gaps in the source data, and instrumentation added 28 Oct 2026")
st.markdown(
    md_table(
        [
            ["No approval timestamp", "Wait and notice are estimates", "`booking_events`: trigger on `bookings` logs each status change with the wait at decision time"],
            ["Declined requests are hard-deleted", "Decline rate cannot be measured", "`booking_events` logs `declined` when the row is deleted"],
            ["Admin-entered rows inferred", "Heuristic exclusion", "`booking_events` logs `admin_created` directly"],
            ["No form analytics", "Drop-off unknown", "`funnel_events`: hourly counts of page view → form open → review → verification → submitted, after consent"],
        ],
        ["Gap", "Effect on this report", "Fix"],
    )
)
st.caption(
    f"Neither new table stores booking ids, names, titles, notes or IP addresses. The next release "
    f"({NEXT_RELEASE}) will use them for exact figures."
)

st.markdown(
    "The approval estimate was checked on 4 Nov 2026 against the event log and the admin chat. All four "
    "approvals logged since 28 Oct matched the estimate to the second, and all five avoidable-late requests "
    "had a ping in the admin chat, which confirms they came through the site."
)
st.markdown(
    "The check also corrected the method. The estimate used to take the latest update across a request's "
    "rows, which counted later edits as waiting time, so a 4.5-hour wait was recorded as 7.2 days because one "
    "session was edited a week after approval. It now takes the earliest update. On the 2 Nov snapshot, that "
    "moved the median wait from 1.9 to 1.7 hours, the 90th percentile from 48.7 to 46.5 hours, and avoidable "
    "late notice from 5 of 46 to 5 of 45."
)
st.markdown(
    "Single-session requests have no other rows to compare, so 57 nightly backups from 16 Sep were used "
    "instead. None of the 46 approved in that time was edited on a later night, but one admin entry edited "
    "later was found counted as public. Removing it would make avoidable late notice 5 of 44, and the figures "
    "here keep it in. Same-day edits and anything before 16 Sep stay unchecked until the event log replaces "
    "the estimate in the next release."
)

# 9 ─────────────────────────────────────────────────────────────────────────
st.header("9. Findings and actions")
st.caption("The evidence below uses all-time figures unless stated.")
slow_all = ALL["windows"]["median"].idxmax()
st.markdown(
    md_table(
        [
            [
                "1",
                "A minority of planned-ahead requests are approved late."
                if ka["avoidable_late"]
                else "Planned-ahead requests are all approved in good time.",
                f"{int(ka['avoidable_late'])} of {int(ka['booked_48h_ahead'])} ({pct(ka['avoidable_late'], ka['booked_48h_ahead'])})",
                "A reminder to admins went live on 6 Nov 2026, as a trial until about 18 Dec."
                if ka["avoidable_late"]
                else "None needed; keep watching the measure.",
                "Made early, approved late, exact from the event log",
            ],
            [
                "2",
                "Requests sent late at night wait longest.",
                f"Median {duration(ALL['windows'].loc[slow_all, 'median'])}, {int(ALL['windows'].loc[slow_all, 'n'])} requests",
                "None. Consistent with admin availability overnight.",
                "–",
            ],
            [
                "3",
                f"Demand has {growth(ratio)}" + (", partly from the launch settling in and term time" if ratio > 1.15 else "") + ".",
                f"{ratio:.1f}× July",
                "Monitor monthly.",
                "Requests per week",
            ],
            [
                "4",
                f"{now_busiest}.",
                f"{last_row.min():.0f}% of hours free, latest four weeks",
                "Monitor monthly.",
                "Free evening hours",
            ],
            [
                "5",
                "Decline rate and form conversion are unmeasured.",
                "Not recorded before 28 Oct",
                "Report in the next release.",
                "Event log, funnel counts",
            ],
        ],
        ["#", "Finding", "Evidence", "Action", "Metric"],
    )
)

# 10 ─────────────────────────────────────────────────────────────────────────
st.header("10. Looking ahead")
st.markdown(
    "A reminder for pending requests started on 6 Nov 2026 as a six-week trial until about 18 Dec. Each morning "
    "it tells admins about any request made at least two days ahead that is still pending one to two days "
    "before its first session. The event log will measure late approvals exactly, though about 20 qualifying "
    "requests can only give a rough idea of the effect."
)
st.markdown(
    "The findings also point to a few other changes worth building, each with a number from this report to "
    "judge it by."
)
st.markdown(
    f"""
- **Availability hints on the booking form.** The data behind section 5 could show bookers which evenings
  tend to be full ({joined(tightest)} in the latest four weeks) and which have room ({joined(roomiest)}),
  spreading demand before clashes happen. It would change what visitors see, so it is a decision for the
  committee.
- **Fair use of peak evenings.** If {joined(tightest)} evenings keep
  filling up, a weekly limit per band on {'those evenings' if many_tight else 'that evening'} would keep the room
  fair. The share of free evening hours shows when it becomes necessary.
- **A simpler booking form.** The form-step counts that started on 28 Oct will show which step loses the
  most visitors, so the next change to the form can target that step.
"""
)
st.markdown(
    f"The next release ({NEXT_RELEASE}) replaces the estimated approval times with exact ones and adds the "
    f"first decline-rate and form-conversion figures, giving each of these changes a proper baseline to be "
    f"measured against."
)

# 11 ─────────────────────────────────────────────────────────────────────────
st.header("11. Method and reproducibility")
st.markdown(
    f"The data runs from Postgres through the SQL files in `sql/` to the aggregate CSVs in `data/`, which "
    f"pandas and Plotly turn into this Streamlit report. Each CSV comes from the SQL file with the same "
    f"number, and most hold one block of rows per period, so the period filter only selects rows and "
    f"never recalculates from finer data.\n\n"
    f"With {int(ka['public_approved'])} public requests in total, the samples are small. The report "
    f"therefore uses medians and percentiles rather than averages for waits and lead times, and makes no "
    f"claims of statistical significance. The repository holds aggregate counts only, with no names, "
    f"booking titles, notes or individual records, so the checks in section 8 that read the backups and "
    f"the admin chat cannot be repeated from it."
)
st.caption(f"Snapshot {SNAPSHOT}. Next release {NEXT_RELEASE}. [Source and SQL]({REPO_URL}).")

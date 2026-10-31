"""Band room booking report.

Descriptive analysis of a band-room booking database: demand, room usage, booking
behaviour, approval latency and data quality. Every figure is computed from the
aggregate CSVs in data/, produced by the SQL in sql/. There is no row-level data in
this repo, so a new snapshot updates every table, chart and sentence together.

Most datasets carry a `period` column (all time, last 8 weeks, last 4 weeks); the
period filter picks rows, it never recomputes from finer data.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).parent / "data"
SNAPSHOT = "1 Nov 2026"
NEXT_RELEASE = "late Nov 2026"
REPO_URL = "https://github.com/rtjw42/band-room-analytics"
PERIODS = ["All time", "Last 8 weeks", "Last 4 weeks"]
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
def load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"{name}.csv")


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

DAY = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
DAYS = list(DAY)


def num(x: float) -> str:
    """62.5 -> '62.5', 20.0 -> '20'."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "–"


def date(d) -> str:
    return pd.to_datetime(d).strftime("%-d %b")


def md_table(rows: list[list], header: list[str]) -> str:
    """Markdown table: text cells wrap instead of truncating, unlike st.dataframe."""
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def for_period(period: str) -> dict:
    """Everything the report needs for one period, sliced and derived."""
    k = kpis.loc[period]
    heat = heat_all[heat_all["period"] == period]
    weeks = int(heat["weeks"].iloc[0])
    grid = heat.pivot(index="hour", columns="weekday_name", values="booked_hours")[DAYS]
    evening = grid.loc[19:23]
    occupancy = 100 * evening.sum() / (weeks * 5)  # per weekday
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
        "usage_start": pd.to_datetime(k["period_end"]) - pd.Timedelta(days=7 * weeks - 1),
        "request_weeks": ((pd.to_datetime(k["period_end"]) - pd.to_datetime(k["period_start"])).days + 1) / 7,
        "grid": grid,
        "slots": int(grid.values.sum()),
        "evening_share": 100 * evening.values.sum() / grid.values.sum(),
        "occupancy": occupancy,
        "occupancy_overall": 100 * evening.values.sum() / (weeks * 35),
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
free_roll = 100 - 100 * used_roll / (WINDOW * 5)
labels = [date(w + pd.Timedelta(days=6)) for w in free_roll.index]
first_free = 100 - 100 * used_roll.iloc[0].sum() / (WINDOW * 35)
last_free = 100 - 100 * used_roll.iloc[-1].sum() / (WINDOW * 35)
trend = "had fallen to" if last_free < first_free else "had risen to" if last_free > first_free else "was unchanged at"
last_row = free_roll.iloc[-1]
tightest = [DAY[d] for d, v in last_row.items() if v == last_row.min()]
roomiest = [DAY[d] for d, v in last_row.items() if v == last_row.max()]
ka = ALL["k"]
wait_summary = ALL["dist"].loc[2]


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
    f"This report covers the band room's booking database as of {SNAPSHOT} (Singapore time). Each "
    f"period ends with the last complete week, figures count requests unless stated otherwise, and "
    f"approval times are estimates, as section 2 explains."
)

free_change = (
    "Evenings are filling up: the share of evening slots left free fell"
    if last_free < first_free
    else "The share of evening slots left free went"
)
quick = "Approvals are usually quick, with a median wait of" if wait_summary["median"] < 6 else "The median approval wait is"
with st.container(border=True):
    st.markdown("**In brief**")
    st.markdown(
        f"Since regular use began in July, demand for the band room has {growth(recent4 / july)}, from "
        f"{num(july)} to {num(recent4)} requests a week, and {num(ALL['evening_share'])}% of the room's use "
        f"falls between 7pm and midnight. {free_change} from {first_free:.0f}% in the four weeks to {labels[0]} "
        f"to {last_free:.0f}% in the four weeks to {labels[-1]}, with {joined(tightest)} now the tightest. "
        f"{quick} {num(wait_summary['median'])} hours, but one request in ten waits {num(wait_summary['p90'])} hours "
        f"or more, and {int(ka['avoidable_late'])} of {int(ka['booked_48h_ahead'])} requests made at least two "
        f"days ahead still got less than a day's notice. Section 10 sets out what these findings could feed into."
    )
    st.caption("This summary uses all-time figures; the period filter below does not change it.")

period = st.segmented_control("Period", PERIODS, default=PERIODS[0], key="period") or PERIODS[0]
P = ALL if period == PERIODS[0] else for_period(period)
k, d = P["k"], P["dist"]
st.caption(
    f"Showing requests submitted between {date(k['period_start'])} and {date(k['period_end'])}, and "
    f"sessions held between {date(P['usage_start'])} and {date(k['period_end'])} ({P['weeks']} weeks). "
    f"The demand chart, the availability animation and sections 8 to 10 always cover the full history."
)
small = [w for w, s in P["windows"].iterrows() if s["n"] < SMALL_N]

public_n = int(k["public_approved"])
displaced = get(P["outcomes"], "Bumped", "sessions")
lead_d, wait_d, length_d = d.loc[1], d.loc[2], d.loc[4]
busiest, quietest = P["occupancy"].idxmax(), P["occupancy"].idxmin()
over = "the whole period" if period == PERIODS[0] else f"the {period.lower()}"



# 1 ─────────────────────────────────────────────────────────────────────────
st.header("1. Summary")
figure(f"Table 1. Key metrics, {period.lower()}")
st.markdown(
    md_table(
        [
            ["Requests", int(k["requests"]), f"{num(k['requests'] / P['request_weeks'])} per week"],
            ["Public requests, approved", public_n, "Requested through the site, then approved"],
            ["Admin-entered requests", int(k["admin_entered"]), "Inserted already approved"],
            ["Hour slots in use", P["slots"], f"{num(P['evening_share'])}% of them in 19:00–24:00"],
            ["Evening occupancy", f"{num(P['occupancy_overall'])}%", f"Of {P['weeks'] * 35} evening hour slots"],
            ["Median lead time", f"{num(lead_d['median'])} days", f"n = {int(lead_d['n'])}"],
            ["Median approval wait (est.)", f"{num(wait_d['median'])} h", f"n = {int(wait_d['n'])}"],
            ["90th percentile approval wait (est.)", f"{num(wait_d['p90'])} h", f"n = {int(wait_d['n'])}"],
            ["Approved < 24 h before first session (est.)", pct(k["under_24h"], public_n), f"{int(k['under_24h'])} of {public_n}"],
            ["Avoidable late notice (est.)", pct(k["avoidable_late"], k["booked_48h_ahead"]), f"{int(k['avoidable_late'])} of {int(k['booked_48h_ahead'])} booked ≥ 48 h ahead"],
            ["Displaced sessions", displaced, "Replaced by an overlapping approval"],
        ],
        ["Metric", "Value", "Base"],
    )
)

figure(f"Table 2. Duration distributions, {period.lower()}")
st.dataframe(
    d[["metric", "unit", "n", "p25", "median", "p75", "p90", "min", "max"]].rename(
        columns={"metric": "Metric", "unit": "Unit", "median": "Median", "min": "Min", "max": "Max"}
    ),
    hide_index=True,
    width="stretch",
)
st.caption(
    "Lead time, wait and notice cover requests made through the site; session length covers the "
    "approved sessions held in the period."
)

# 2 ─────────────────────────────────────────────────────────────────────────
st.header("2. Data and definitions")
st.markdown(
    "The report draws on two tables. `bookings` has one row per session, with its start and end, "
    "its status (`pending`, `approved` or `rejected`) and when it was created and last updated. "
    "`booking_groups` links the sessions of a multi-date request and records whether the dates were "
    "hand-picked (`custom`) or a weekly repeat (`pattern`). Everything was aggregated in SQL before "
    "export, so no individual booking leaves the database."
)
st.markdown(
    md_table(
        [
            ["Session", "One row in `bookings`."],
            ["Request", "One submission: `coalesce(group_id, id)`. A multi-date or weekly request counts once."],
            ["Public request", "Approved request with `updated_at > created_at`: submitted, then approved by an admin."],
            ["Admin-entered request", "Approved request with `updated_at = created_at`: inserted already approved. Heuristic: an admin-entered booking edited later counts as public."],
            ["Approval time (est.)", "`max(updated_at)` across the request's rows. Overstates the wait when a booking is edited after approval."],
            ["Lead time", "First session start minus submission time."],
            ["Notice", "First session start minus approval time (est.)."],
            ["Avoidable late notice", "Notice < 24 h among requests with lead time ≥ 48 h."],
            ["Period", "All time, last 8 weeks or last 4 weeks, ending on the last complete week. Requests fall in the period they were submitted; sessions in the period they were held. Upcoming sessions are excluded."],
            ["Hour slot in use", "A weekday-hour slot that an approved session occupied at least partly. Two sessions sharing a slot count it once."],
            ["Evening occupancy", "Evening (19:00–24:00) hour slots in use ÷ evening hour slots available in the period."],
            ["Submission window", "Weekend: Fri 18:00 – Sun 23:59. Weekday late night: 23:00–07:00. Weekday daytime: the rest."],
            ["Week", "Monday start, SGT."],
        ],
        ["Term", "Definition"],
    )
)

# 3 ─────────────────────────────────────────────────────────────────────────
st.header("3. Demand")
figure(f"Figure 1. Requests per week by submission date (n = {int(weekly['requests'].sum())})")
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
    "The chart always shows every week, with the selected period shaded. The grey bar is the current "
    "week, which is still in progress and left out of the averages."
)
peak = complete.loc[complete["requests"].idxmax()]
first_session = ALL["usage_start"]
total_requests = int(weekly["requests"].sum())
st.markdown(
    f"July averaged {num(july)} requests a week; the last four complete weeks averaged "
    f"{num(recent4)}, about {recent4 / july:.1f} times as many. The busiest week so far was the week of "
    f"{date(peak['week_start'])}, with {int(peak['requests'])} requests. Part of this growth is the room "
    f"settling in after launch: every approved session falls on or after the week of "
    f"{date(first_session)}, and the {int(dq.loc[8, 'affected'])} sessions scheduled before then were "
    f"all later displaced.\n\n"
    f"Of the {total_requests} requests, {int(weekly['likely_admin_entered'].sum())} were entered "
    f"directly by admins rather than through the site. They count towards demand here but are left out "
    f"of the wait and lead-time figures, which only apply to requests that went through the approval queue."
)

# 4 ─────────────────────────────────────────────────────────────────────────
st.header("4. Room usage")
view = st.segmented_control("Heatmap shows", ["Hours in use", "Share of weeks in use"], default="Hours in use", key="heat_view") or "Hours in use"
grid = P["grid"]
share = view == "Share of weeks in use"
z = 100 * grid / P["weeks"] if share else grid
figure(
    f"Figure 2. {'Share of weeks each hour slot was in use' if share else 'Hour slots in use'} "
    f"by weekday and hour, SGT, {period.lower()}" + (f" ({P['weeks']} weeks)" if period == PERIODS[0] else "")
)
steps = len(HEAT) - 1
fig = go.Figure(
    go.Heatmap(
        z=z.where(grid > 0).values,  # never-used slots stay blank
        x=DAYS,
        y=[f"{h:02d}:00" for h in grid.index],
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
show(fig, z.round(1).reset_index().rename(columns={"hour": "Hour"}), 620)
st.caption("Blank squares were never in use in the period. A slot counts as in use when a session occupies any part of it.")

figure(f"Figure 3. Evening occupancy by weekday, {period.lower()}")
occ = P["occupancy"]
fig = single_series_bars(
    occ.index,
    occ.values,
    "%{x}: %{y:.1f}% of evening hour slots in use",
    colors=[ACCENT if day == busiest else MUTED for day in occ.index],
    labels=[f"{num(v)}%" if day in (busiest, quietest) else None for day, v in occ.items()],
)
fig.update_yaxes(range=[0, 100], ticksuffix="%")
show(
    fig,
    pd.DataFrame(
        {
            "Day": occ.index,
            "Evening slots in use": grid.loc[19:23].sum().values,
            "Evening slots available": P["weeks"] * 5,
            "Occupancy (%)": occ.round(1).values,
        }
    ),
    300,
)

figure(f"Figure 4. Session length, {period.lower()} (n = {int(length_d['n'])})")
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
    unused_text = f", and no slot between {unused[0]:02d}:00 and {unused[-1]:02d}:59 was used on any day"
else:
    unused_text = f", and no slot at {joined([f'{h:02d}:00' for h in unused])} was used on any day"
flat_use = grid.stack()
peak_slots = [f"{DAY[d]} {h:02d}:00" for (h, d), v in flat_use.items() if v == flat_use.max()]
in_use = f"in use in {int(flat_use.max())} of {P['weeks']} weeks"
if len(peak_slots) == 1:
    peak_text = f"The single busiest slot was {peak_slots[0]}, {in_use}."
elif len(peak_slots) <= 3:
    peak_text = f"The busiest slots were {joined(peak_slots)}, each {in_use}."
else:
    peak_text = f"No single slot stood out: {WORDS.get(len(peak_slots), str(len(peak_slots))).lower()} slots tied as the busiest, each {in_use}."
if length_d["p25"] == length_d["p75"]:
    spread = f"at least half of them ran exactly {num(length_d['p25'])} hours"
else:
    spread = f"the middle half ran between {num(length_d['p25'])} and {num(length_d['p75'])} hours"
st.markdown(
    f"Most use falls in the evening: {num(P['evening_share'])}% of the hour slots in use were between "
    f"7pm and midnight{unused_text}. {peak_text}\n\n"
    f"Across the week, {num(P['occupancy_overall'])}% of evening slots were in use. {DAY[busiest]} "
    f"evenings were the fullest at {num(occ[busiest])}%, and {DAY[quietest]} evenings the quietest at "
    f"{num(occ[quietest])}%. Sessions had a median length of {num(length_d['median'])} hours; {spread}, "
    f"and the longest ran {num(length_d['max'])} hours."
)

# 5 ─────────────────────────────────────────────────────────────────────────
st.header("5. Room availability")


def availability_bars(row: pd.Series) -> go.Bar:
    low = row.min()
    return go.Bar(
        x=DAYS,
        y=row.values,
        marker=dict(color=[ACCENT if v == low else MUTED for v in row.values], cornerradius=4),
        text=[f"{v:.0f}%" if v == low else "" for v in row.values],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{x}: %{y:.0f}% of evening slots free<extra></extra>",
    )


figure("Figure 5. Share of evening slots free by weekday, four weeks at a time")
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
    free_roll.round(1).assign(window_end=labels).reset_index(drop=True)[["window_end", *DAYS]].rename(columns={"window_end": "Four weeks to"}),
    420,
    top=56,
    bottom=96,
)
st.caption(
    "Each bar covers four weeks, so one unusually busy or quiet week does not swing it. The dark bar marks "
    "the day with the least room. The chart opens on the latest four weeks; press Play to step through the "
    "whole history, whatever the period filter."
)

st.markdown(
    f"In the four weeks to {labels[0]}, {first_free:.0f}% of evening slots were free; by the four weeks to "
    f"{labels[-1]}, that {trend} {last_free:.0f}%. In the latest window, {joined(tightest)} "
    f"{'had' if len(tightest) == 1 else 'shared'} the least room, with {last_row.min():.0f}% of evening slots free."
)

free_weeks = P["weeks"] - grid  # weeks each hour slot was free in the selected period
evening_free = free_weeks.loc[19:23]


def hours_at(col: pd.Series, value: int) -> str:
    """Every hour tied at `value`, so a tie is never reported as a single winner."""
    hits = [f"{h:02d}:00" for h, v in col.items() if v == value]
    return "every hour" if len(hits) == len(col) else ", ".join(hits)


flat = evening_free.stack()
hardest = [f"{DAY[d]} {h:02d}:00" for (h, d), v in flat.items() if v == flat.min()]
day_free = 100 * evening_free.sum() / (P["weeks"] * 5)
easiest = [DAY[d] for d, v in day_free.items() if v == day_free.max()]
always = int((flat == P["weeks"]).sum())
one = len(hardest) == 1
hard_free = (
    f"{'which was' if one else 'which were'} taken every week"
    if flat.min() == 0
    else f"free in only {int(flat.min())} of {P['weeks']} weeks"
)
st.markdown(
    f"Over {over}"
    + (f" ({P['weeks']} weeks)" if period == PERIODS[0] else "")
    + f", the hardest evening {'slot' if one else 'slots'} to get {'was' if one else 'were'} "
    f"{joined(hardest)}, {hard_free}. {joined(easiest)} had the most room, "
    f"{'with' if len(easiest) == 1 else 'each with'} {day_free.max():.0f}% of evening slots free"
    + (
        f", and {always} of the 35 evening slots {'was' if always == 1 else 'were'} free every week."
        if always
        else ", though no evening slot was free every week."
    )
)
if period == PERIODS[0]:
    st.caption("The whole period includes the quieter early weeks; Last 8 weeks gives the current picture.")
with st.expander(f"Evening availability by day, {period.lower()}"):
    st.markdown(
        md_table(
            [
                [
                    DAY[d],
                    f"{100 * evening_free[d].sum() / (P['weeks'] * 5):.0f}%",
                    f"{hours_at(evening_free[d], evening_free[d].min())} (free {int(evening_free[d].min())} of {P['weeks']})",
                    f"{hours_at(evening_free[d], evening_free[d].max())} (free {int(evening_free[d].max())} of {P['weeks']})",
                ]
                for d in DAYS
            ],
            ["Day", "Evening slots free", "Hardest slot", "Easiest slot"],
        )
    )

# 6 ─────────────────────────────────────────────────────────────────────────
st.header("6. Booking behaviour")
lead = P["lead"]
figure(f"Figure 6. Lead time, public requests, {period.lower()} (n = {int(lead_d['n'])})")
show(
    single_series_bars(lead["bin"], lead["requests"], "%{y}: %{x} requests", horizontal=True),
    lead[["bin", "requests"]].rename(columns={"bin": "Lead time", "requests": "Requests"}),
    280,
)
types = P["types"]
approved_n = int(types["requests"].sum())
figure(f"Table 3. Request type, approved requests, {period.lower()}")
st.markdown(
    md_table(
        [[label.capitalize(), int(r["requests"]), pct(r["requests"], approved_n), int(r["sessions"])] for label, r in types.iterrows()],
        ["Type", "Requests", "Share", "Sessions"],
    )
)
st.caption("Custom requests cover several hand-picked dates; pattern requests repeat weekly.")
under_day = int(lead.loc[lead["bin_order"] == 1, "requests"].sum())
multi = types.drop(index="one-off", errors="ignore")
multi_n = int(multi["requests"].sum())
multi_text = (
    f"Most requests are for a single session; only {multi_n} of {approved_n} approved requests "
    f"({pct(multi_n, approved_n)}) covered several dates, adding up to {int(multi['sessions'].sum())} sessions."
    if multi_n
    else "Every approved request in this period was for a single session."
)
st.markdown(
    f"The median request came {num(lead_d['median'])} days before its first session. Half came between "
    f"{num(lead_d['p25'])} and {num(lead_d['p75'])} days ahead, and only one in ten came more than "
    f"{num(lead_d['p90'])} days ahead. Of the {int(lead_d['n'])} requests, {under_day} "
    f"({pct(under_day, lead_d['n'])}) arrived less than a day before the session they were for.\n\n"
    + multi_text
)

# 7 ─────────────────────────────────────────────────────────────────────────
st.header("7. Approval process")
windows, wait = P["windows"], P["wait"]
figure(f"Figure 7. Estimated approval wait by submission window, {period.lower()} (n = {public_n})")
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
        x=0, y=w, xanchor="left", yanchor="bottom", yshift=24, showarrow=False, text=f"<b>{w}</b>  n = {int(s['n'])}"
    )
fig.update_layout(barmode="stack", bargap=0.6, legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom", traceorder="normal"))
fig.update_xaxes(range=[0, 100], ticksuffix="%", showgrid=False)
fig.update_yaxes(autorange="reversed", showticklabels=False)
show(
    fig,
    wait[["submitted_window", "wait_bin", "requests", "window_requests"]].rename(
        columns={"submitted_window": "Window", "wait_bin": "Wait", "requests": "Requests", "window_requests": "Window n"}
    ),
    340,
    top=64,
)

figure(f"Table 4. Approval wait by submission window (est.), {period.lower()}")
st.markdown(
    md_table(
        [
            [w, int(s["n"]), f"{num(s['median'])} h" if pd.notna(s["median"]) else "–", pct(s["under_1h"], s["n"]), pct(s["over_24h"], s["n"])]
            for w, s in windows.iterrows()
        ],
        ["Window", "n", "Median wait", "Within 1 h", "Over 24 h"],
    )
)
if small:
    names = joined([w.lower() for w in small])
    st.caption(
        f"Fewer than {SMALL_N} requests fall in the {names} {'window' if len(small) == 1 else 'windows'}, "
        f"so treat {'its' if len(small) == 1 else 'their'} figures as indicative."
    )
slowest = windows["median"].idxmax()
fastest = windows["median"].idxmin()
SENT = {
    "Weekday daytime": "requests sent during the weekday daytime",
    "Weekday late night": "requests sent late on weeknights",
    "Weekend": "requests sent at the weekend",
}
after = int(k["approved_after_start"])
after_text = (
    f"\n\nIn {after} {'case' if after == 1 else 'cases'}, the estimated approval time came after the "
    f"first session had already started; section 8 covers why that can happen."
    if after
    else ""
)
st.markdown(
    f"The median wait was {num(wait_d['median'])} hours and three in four requests were approved within "
    f"{num(wait_d['p75'])} hours, but one in ten waited {num(wait_d['p90'])} hours or more, and the "
    f"longest took {num(wait_d['max'])} hours. How long a request waited depended on when it was sent: "
    f"{SENT[slowest]} had the longest median wait at {num(windows.loc[slowest, 'median'])} hours "
    f"(n = {int(windows.loc[slowest, 'n'])}), against {num(windows.loc[fastest, 'median'])} hours for "
    f"{SENT[fastest]}.\n\n"
    f"Long waits matter most when the session is close. Of {public_n} requests, {int(k['under_24h'])} "
    f"({pct(k['under_24h'], public_n)}) were approved less than a day before their first session, but "
    f"{int(k['under_24h'] - k['avoidable_late'])} of those had been submitted less than two days ahead, "
    f"which left little room for a faster answer. Among requests submitted at least two days ahead, "
    f"{int(k['avoidable_late'])} of {int(k['booked_48h_ahead'])} "
    f"({pct(k['avoidable_late'], k['booked_48h_ahead'])}) still got under a day's notice; these are the "
    f"cases a faster process could prevent."
    + after_text
)

# 8 ─────────────────────────────────────────────────────────────────────────
st.header("8. Data quality and instrumentation")
figure("Table 5. Data-quality checks, all records")
impact = {
    1: ("Excluded from wait and lead-time metrics; identified by a heuristic.", "Exact from 28 Oct (event log)"),
    2: ("Inflate the wait and notice tails. Likely post-session edits or retroactive approvals.", "Unverified"),
    3: ("Part of an admin-entered request, so excluded from lead-time figures.", "No effect"),
    4: ("Weight the heatmap; may include entry errors.", "Unverified"),
    5: ("22:00–06:00 sessions in July; possibly AM/PM entry errors.", "Unverified"),
    6: ("Approving an overlapping request replaces the earlier approval.", "Logged as `bumped` from 28 Oct"),
    7: (
        "None pending at snapshot time." if dq.loc[7, "affected"] == 0
        else "Awaiting a decision at snapshot time; not part of any period figure.",
        "–",
    ),
    8: ("Every displacement predates regular use; none since.", "Historical"),
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
    "can differ slightly from the period figures above; admin-entered requests are one example."
)

figure("Table 6. Gaps in the source data, and instrumentation added 28 Oct 2026")
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

# 9 ─────────────────────────────────────────────────────────────────────────
st.header("9. Findings and actions")
st.caption("The evidence below uses all-time figures, and the last 8 weeks where stated.")
ra = for_period("Last 8 weeks")
slow_all = ALL["windows"]["median"].idxmax()
busy8 = ra["occupancy"].idxmax()
st.markdown(
    md_table(
        [
            [
                "1",
                "A minority of planned-ahead requests are approved late.",
                f"{int(ka['avoidable_late'])} of {int(ka['booked_48h_ahead'])} ({pct(ka['avoidable_late'], ka['booked_48h_ahead'])})",
                "Remind admins when a request is pending and its first session is < 48 h away.",
                "Avoidable late notice, exact from the event log",
            ],
            [
                "2",
                "Late-night submissions wait longest.",
                f"Median {num(ALL['windows'].loc[slow_all, 'median'])} h, n = {int(ALL['windows'].loc[slow_all, 'n'])}",
                "None. Consistent with admin availability overnight.",
                "–",
            ],
            [
                "3",
                f"Demand has roughly doubled, partly as post-launch ramp-up; {DAY[busy8]} evenings are the most occupied.",
                f"{recent4 / july:.1f}× July; last 8 weeks: {DAY[busy8]} {num(ra['occupancy'][busy8])}% vs "
                f"{num(ra['occupancy_overall'])}% all evenings; latest four weeks: {joined(tightest)} at "
                f"{100 - last_row.min():.0f}%; 0 displaced sessions since regular use began",
                f"Monitor {DAY[busy8]} occupancy and displaced sessions monthly.",
                "Evening occupancy, displaced sessions",
            ],
            [
                "4",
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
plural = len(tightest) > 1
st.markdown(
    "The findings point to a few changes worth building next, each with a number from this report to judge "
    "it by."
)
st.markdown(
    f"""
- **A reminder for pending requests.** A nudge to admins when a request is still pending and its first
  session is less than 48 hours away targets the {int(ka['avoidable_late'])} of {int(ka['booked_48h_ahead'])}
  planned-ahead requests that got late notice, without adding work for the rest. The event log added on
  28 Oct measures its effect exactly.
- **Availability hints on the booking form.** The data behind section 5 could show bookers which evenings
  tend to be full ({joined(tightest)} in the latest four weeks) and which have room ({joined(roomiest)}),
  spreading demand before clashes happen. It would change what visitors see, so it is a decision for the
  committee.
- **Fair use of peak evenings.** If {joined(tightest)} evenings keep
  filling up, a weekly limit per band on {'those evenings' if plural else 'that evening'} would keep the room
  fair. Evening occupancy and displaced sessions show when it becomes necessary.
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
    f"therefore uses medians and percentiles rather than averages, and makes no claims of statistical "
    f"significance. The repository holds aggregate counts only, with no names, booking titles, notes "
    f"or individual records."
)
st.caption(f"Snapshot {SNAPSHOT}. Next release {NEXT_RELEASE}. [Source and SQL]({REPO_URL}).")

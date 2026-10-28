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
SNAPSHOT = "28 Oct 2026"
NEXT_RELEASE = "late Nov 2026"
REPO_URL = "https://github.com/rtjw42/band-room-analytics"
PERIODS = ["All time", "Last 8 weeks", "Last 4 weeks"]
SMALL_N = 10

st.set_page_config(page_title="Band room booking report", layout="centered")


# ── Colours ──────────────────────────────────────────────────────────────────
# The band room site's palette: ochre-to-cocoa on cream, ochre-to-sand on warm
# charcoal; never cold blue. Each set passed the colour-blind and contrast checks
# against the site's own surfaces (#f9f6f1 light, #1d1916 dark). The 4-week mean is
# a reference line of the same measure, so it wears the text colour, not a hue.
def is_dark() -> bool:
    theme = getattr(st.context, "theme", None)
    return getattr(theme, "type", "light") == "dark"


if is_dark():
    ACCENT, REFERENCE, MUTED, BG = "#b47a3a", "#efeae1", "#4a4038", "#1d1916"
    SHADE = "rgba(180, 122, 58, 0.16)"
    RAMP = ["#6e4c2d", "#93683a", "#b88947", "#d9ae63", "#f2d6a0"]
    HEAT = ["#6e4c2d", "#86603a", "#a07646", "#ba8d52", "#d2a662", "#e6c07c", "#f3d9a6"]
else:
    ACCENT, REFERENCE, MUTED, BG = "#b0742f", "#372c25", "#d8cdbd", "#f9f6f1"
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


def show(fig: go.Figure, table: pd.DataFrame, height: int, top: int = 40) -> None:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=top, b=8),
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


# ── Report ───────────────────────────────────────────────────────────────────
st.title("Band room booking report")
st.caption(
    f"Source: booking database (Postgres). Snapshot: {SNAPSHOT}, SGT. Periods end on the last "
    f"complete week. Unit: request unless stated. Approval times are estimated (section 2)."
)

period = st.segmented_control("Period", PERIODS, default=PERIODS[0], key="period") or PERIODS[0]
P = for_period(period)
ALL = P if period == PERIODS[0] else for_period(PERIODS[0])
k, d = P["k"], P["dist"]
st.caption(
    f"Requests submitted {date(k['period_start'])} – {date(k['period_end'])}. Sessions held "
    f"{date(P['usage_start'])} – {date(k['period_end'])} ({P['weeks']} weeks). Sections 3, 7 and 8 "
    f"are not filtered."
)
small = [w for w, s in P["windows"].iterrows() if s["n"] < SMALL_N]

public_n = int(k["public_approved"])
displaced = get(P["outcomes"], "Bumped", "sessions")
lead_d, wait_d, length_d = d.loc[1], d.loc[2], d.loc[4]
busiest, quietest = P["occupancy"].idxmax(), P["occupancy"].idxmin()

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
st.caption("Request-level rows cover public requests only. Session length covers approved sessions held in the period.")

# 2 ─────────────────────────────────────────────────────────────────────────
st.header("2. Data and definitions")
st.markdown(
    "Two tables feed this report. `bookings` holds one row per session (start, end, status "
    "`pending` / `approved` / `rejected`, `created_at`, `updated_at`, `group_id`). "
    "`booking_groups` holds one row per multi-date request (`kind`: `custom` or `pattern`). "
    "All figures were aggregated in SQL before export."
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
complete = weekly[~weekly["partial_week"]]
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
    "All weeks, whatever the period filter; the shaded band marks the selected period. "
    "Grey: current week, incomplete and excluded from means."
)
recent4 = complete.tail(4)["requests"].mean()
july = complete.loc[complete["week_start"].dt.month == 7, "requests"].mean()
peak = complete.loc[complete["requests"].idxmax()]
first_session = ALL["usage_start"]
st.markdown(
    f"""
- Mean weekly requests: {num(july)} in July, {num(recent4)} over the last 4 complete weeks
  ({recent4 / july:.1f}×).
- Highest week: {date(peak['week_start'])}, {int(peak['requests'])} requests.
- Regular use starts in the week of {date(first_session)}: every approved session falls on or after
  it. The {int(dq.loc[8, 'affected'])} sessions scheduled before then were all displaced, so
  part of the rise since July is ramp-up after launch.
- Admin-entered: {int(weekly['likely_admin_entered'].sum())} of {int(weekly['requests'].sum())} requests.
  Included in demand, excluded from wait and lead-time figures.
"""
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
st.caption("Blank: never in use in the period. A slot counts when a session occupies any part of it.")

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
contiguous = bool(unused) and unused == list(range(unused[0], unused[-1] + 1))
unused_label = f"{unused[0]:02d}:00–{unused[-1]:02d}:59" if contiguous else ", ".join(f"{h:02d}:00" for h in unused) or "no hour"
peak_day, peak_hour = grid.stack().idxmax()[::-1]
st.markdown(
    f"""
- {num(P['evening_share'])}% of hour slots in use fall in 19:00–24:00. Busiest slot:
  {DAY[peak_day]} {peak_hour:02d}:00, in use {int(grid.loc[peak_hour, peak_day])} of {P['weeks']} weeks.
- No slot in use on any day in {unused_label}.
- Evening occupancy: {num(P['occupancy_overall'])}% overall, highest on {DAY[busiest]}
  ({num(occ[busiest])}%), lowest on {DAY[quietest]} ({num(occ[quietest])}%).
- Session length: median {num(length_d['median'])} h, IQR {num(length_d['p25'])}–{num(length_d['p75'])} h,
  max {num(length_d['max'])} h.
"""
)

# 5 ─────────────────────────────────────────────────────────────────────────
st.header("5. Booking behaviour")
lead = P["lead"]
figure(f"Figure 5. Lead time, public requests, {period.lower()} (n = {int(lead_d['n'])})")
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
st.caption("Custom: several hand-picked dates. Pattern: a weekly repeat.")
under_day = int(lead.loc[lead["bin_order"] == 1, "requests"].sum())
multi = types.drop(index="one-off", errors="ignore")
st.markdown(
    f"""
- Lead time: median {num(lead_d['median'])} days, IQR {num(lead_d['p25'])}–{num(lead_d['p75'])} days,
  90th percentile {num(lead_d['p90'])} days.
- {under_day} of {int(lead_d['n'])} public requests ({pct(under_day, lead_d['n'])}) were submitted less
  than a day before the first session.
- Multi-date requests: {int(multi['requests'].sum())} of {approved_n} ({pct(multi['requests'].sum(), approved_n)}),
  covering {int(multi['sessions'].sum())} sessions.
"""
)

# 6 ─────────────────────────────────────────────────────────────────────────
st.header("6. Approval process")
windows, wait = P["windows"], P["wait"]
figure(f"Figure 6. Estimated approval wait by submission window, {period.lower()} (n = {public_n})")
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
    st.caption(f"Fewer than {SMALL_N} requests in: {', '.join(small)}. Treat those shares and medians as indicative.")
slowest = windows["median"].idxmax()
st.markdown(
    f"""
- Approval wait: median {num(wait_d['median'])} h, p75 {num(wait_d['p75'])} h, p90 {num(wait_d['p90'])} h,
  max {num(wait_d['max'])} h.
- Highest median wait by window: {slowest.lower()} ({num(windows.loc[slowest, 'median'])} h,
  n = {int(windows.loc[slowest, 'n'])}).
- Approved less than 24 h before the first session: {int(k['under_24h'])} of {public_n}
  ({pct(k['under_24h'], public_n)}). {int(k['under_24h'] - k['avoidable_late'])} of those were submitted
  less than 48 h ahead.
- Restricted to requests submitted at least 48 h ahead: {int(k['avoidable_late'])} of
  {int(k['booked_48h_ahead'])} ({pct(k['avoidable_late'], k['booked_48h_ahead'])}) still received under 24 h notice.
- Requests with an approval time after the first session started: {int(k['approved_after_start'])} (section 7).
"""
)

# 7 ─────────────────────────────────────────────────────────────────────────
st.header("7. Data quality and instrumentation")
figure("Table 5. Data-quality checks, all records")
impact = {
    1: ("Excluded from wait and lead-time metrics; identified by a heuristic.", "Exact from 28 Oct (event log)"),
    2: ("Inflate the wait and notice tails. Likely post-session edits or retroactive approvals.", "Unverified"),
    3: ("Part of an admin-entered request, so excluded from lead-time figures.", "No effect"),
    4: ("Weight the heatmap; may include entry errors.", "Unverified"),
    5: ("22:00–06:00 sessions in July; possibly AM/PM entry errors.", "Unverified"),
    6: ("Approving an overlapping request replaces the earlier approval.", "Logged as `bumped` from 28 Oct"),
    7: ("None pending at snapshot time.", "–"),
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
    f"Neither new table holds booking ids, names, titles, notes or IP addresses. "
    f"Exact figures from them are scheduled for the next release ({NEXT_RELEASE})."
)

# 8 ─────────────────────────────────────────────────────────────────────────
st.header("8. Findings and actions")
st.caption("Evidence uses all-time figures, plus the last 8 weeks where noted.")
ka, ra = ALL["k"], for_period("Last 8 weeks")
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
                f"Demand has doubled; {DAY[busy8]} evenings are the most occupied.",
                f"{recent4 / july:.1f}× July; last 8 weeks: {DAY[busy8]} {num(ra['occupancy'][busy8])}% vs "
                f"{num(ra['occupancy_overall'])}% all evenings; 0 displaced sessions since regular use began",
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

# 9 ─────────────────────────────────────────────────────────────────────────
st.header("9. Method and reproducibility")
st.markdown(
    f"""
- Pipeline: Postgres → SQL in `sql/` → aggregate CSVs in `data/` → pandas and Plotly → Streamlit.
- Each CSV comes from the SQL file with the same number. Most carry a `period` column; the period
  filter selects rows and recomputes nothing from finer data.
- Sample sizes are small (n = {int(ka['public_approved'])} public requests all time), so the report
  uses medians and percentiles, not means. No significance testing.
- The repo holds aggregate counts only: no names, booking titles, notes or row-level records.
"""
)
st.caption(f"Snapshot {SNAPSHOT}. Next release {NEXT_RELEASE}. [Source and SQL]({REPO_URL}).")

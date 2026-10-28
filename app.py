"""Band room booking report.

Descriptive analysis of a band-room booking database: demand, room usage, booking
behaviour, approval latency and data quality. Every figure is computed from the
aggregate CSVs in data/, produced by the SQL in sql/. There is no row-level data in
this repo, so a new snapshot updates every table, chart and sentence together.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).parent / "data"
SNAPSHOT = "28 Oct 2026"
PERIOD = "29 Apr – 28 Oct 2026"
NEXT_RELEASE = "late Nov 2026"
REPO_URL = ""  # set once the repo is on GitHub

st.set_page_config(page_title="Band room booking report", layout="centered")


# ── Colours ──────────────────────────────────────────────────────────────────
# One blue for single-series charts, grey for de-emphasised bars, orange for the
# trend line. The wait bands use a five-step blue ramp checked for colour-blind
# separation and contrast in both themes; dark mode gets its own steps, not a flip.
def is_dark() -> bool:
    theme = getattr(st.context, "theme", None)
    return getattr(theme, "type", "light") == "dark"


if is_dark():
    ACCENT, TREND, MUTED, BG = "#3987e5", "#d95926", "#4a4945", "#0e1117"
    RAMP = ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"]
    HEAT = ["#104281", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"]
else:
    ACCENT, TREND, MUTED, BG = "#2a78d6", "#eb6834", "#c9c7c0", "#ffffff"
    RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
    HEAT = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


# ── Data ─────────────────────────────────────────────────────────────────────
@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"{name}.csv")


kpi = load("01_kpis").set_index("metric")["value"]
weekly = load("02_weekly_demand")
weekly["week_start"] = pd.to_datetime(weekly["week_start"])
heat = load("03_heatmap")
lead = load("04_lead_time")
wait = load("05_wait_by_window")
mix = load("06_request_mix")
occ = load("07_evening_occupancy")
sessions = load("08_session_length")
dist = load("09_distributions").set_index("sort")
dq = load("10_data_quality").set_index("sort")


def num(x: float) -> str:
    """62.5 -> '62.5', 20.0 -> '20'."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f}%"


def md_table(rows: list[list], header: list[str]) -> str:
    """Markdown table: text cells wrap instead of truncating, unlike st.dataframe."""
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


# Demand
total = int(kpi["Requests"])
public_n = int(kpi["Public requests approved"])
admin_n = int(dq.loc[1, "affected"])
complete = weekly[~weekly["partial_week"]]
recent4 = complete.tail(4)
recent_rate = recent4["requests"].mean()
july_rate = complete.loc[complete["week_start"].dt.month == 7, "requests"].mean()
peak_week = complete.loc[complete["requests"].idxmax()]
zero_weeks = complete[complete["requests"] == 0]

# Usage
evening_share = kpi["Evening share of booked hours"]
booked_hours = int(heat["booked_hours"].sum())
peak_cell = heat.loc[heat["booked_hours"].idxmax()]
by_hour = heat.groupby("hour")["booked_hours"].sum()
unbooked_hours = by_hour[by_hour == 0].index.tolist()
occ_by_day = occ.set_index("weekday_name")["occupancy_pct"]
occ_overall = 100 * occ["booked_slots"].sum() / occ["available_slots"].sum()
occ_start = pd.to_datetime(occ["window_start"].iloc[0]).strftime("%d %b")
occ_end = pd.to_datetime(occ["window_end"].iloc[0]).strftime("%d %b")
DAY = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
busiest, quietest = occ_by_day.idxmax(), occ_by_day.idxmin()

# Behaviour
lead_d, wait_d, notice_d, length_d = (dist.loc[i] for i in (1, 2, 3, 4))
lead_under_day = int(lead.loc[lead["bin_order"] == 1, "requests"].sum())
types = mix[mix["dimension"] == "Type"].set_index("label")
approved_requests = int(types["requests"].sum())
recurring = types.drop(index="one-off", errors="ignore")

# Approvals
under24 = round(kpi["Under 24h notice"] / 100 * public_n)
late_n = int(kpi["Avoidable late notice (count)"])
planned_n = round(late_n / (kpi["Avoidable late notice"] / 100))
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
).T.sort_values("median")


# ── Chart helpers ────────────────────────────────────────────────────────────
def figure(label: str) -> None:
    st.markdown(f"**{label}**")


def show(fig: go.Figure, table: pd.DataFrame, height: int, top: int = 40) -> None:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=top, b=8),
        font=dict(size=13),
        hoverlabel=dict(font_size=13),
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
    f"Source: booking database (Postgres). Period: {PERIOD}. Snapshot: {SNAPSHOT}, SGT. "
    f"Unit: request unless stated. Approval times are estimated (section 2)."
)

# 1 ─────────────────────────────────────────────────────────────────────────
st.header("1. Summary")
figure("Table 1. Key metrics")
st.markdown(
    md_table(
        [
            ["Requests, all outcomes", total, "Since launch"],
            ["Public requests, approved", public_n, "Requested through the site, then approved"],
            ["Admin-entered requests", admin_n, "Inserted already approved"],
            ["Requests per week, last 4 complete weeks", num(recent_rate), f"Weeks from {recent4['week_start'].iloc[0]:%d %b}"],
            ["Requests per week, July", num(july_rate), "4 weeks"],
            ["Booked hours in 19:00–24:00", f"{num(evening_share)}%", f"Of {booked_hours} booked hours"],
            ["Evening occupancy, last 8 weeks", f"{num(occ_overall)}%", f"{int(occ['booked_slots'].sum())} of {int(occ['available_slots'].sum())} evening hours"],
            ["Median lead time", f"{num(lead_d['median'])} days", f"n = {int(lead_d['n'])}"],
            ["Median approval wait (est.)", f"{num(wait_d['median'])} h", f"n = {int(wait_d['n'])}"],
            ["90th percentile approval wait (est.)", f"{num(wait_d['p90'])} h", f"n = {int(wait_d['n'])}"],
            ["Approved < 24 h before first session (est.)", f"{num(kpi['Under 24h notice'])}%", f"{under24} of {public_n}"],
            ["Avoidable late notice (est.)", f"{num(kpi['Avoidable late notice'])}%", f"{late_n} of {planned_n} booked ≥ 48 h ahead"],
            ["Displaced sessions", int(dq.loc[6, "affected"]), "Replaced by an overlapping approval"],
        ],
        ["Metric", "Value", "Base"],
    )
)

figure("Table 2. Duration distributions")
st.dataframe(
    dist[["metric", "unit", "n", "p25", "median", "p75", "p90", "min", "max"]].rename(
        columns={"metric": "Metric", "unit": "Unit", "median": "Median", "min": "Min", "max": "Max"}
    ),
    hide_index=True,
    width="stretch",
)
st.caption("Request-level rows cover public requests only. Session length covers all approved sessions.")

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
            ["Admin-entered request", "Approved request with `updated_at = created_at`: inserted already approved. Heuristic."],
            ["Approval time (est.)", "`max(updated_at)` across the request's rows. Overstates the wait when a booking is edited after approval."],
            ["Lead time", "First session start minus submission time."],
            ["Notice", "First session start minus approval time (est.)."],
            ["Avoidable late notice", "Notice < 24 h among requests with lead time ≥ 48 h."],
            ["Evening", "19:00–24:00 SGT."],
            ["Evening occupancy", "Evening hours used by past approved sessions ÷ evening hours available."],
            ["Submission window", "Weekend: Fri 18:00 – Sun 23:59. Weekday late night: 23:00–07:00. Weekday daytime: the rest."],
            ["Week", "Monday start, SGT."],
        ],
        ["Term", "Definition"],
    )
)

# 3 ─────────────────────────────────────────────────────────────────────────
st.header("3. Demand")
figure(f"Figure 1. Requests per week by submission date (n = {total})")
fig = go.Figure()
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
    line=dict(color=TREND, width=2),
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
st.caption("Grey: current week, incomplete and excluded from means.")
st.markdown(
    f"""
- Mean weekly requests: {num(july_rate)} in July, {num(recent_rate)} over the last 4 complete
  weeks ({recent_rate / july_rate:.1f}×).
- Highest week: {peak_week['week_start']:%d %b}, {int(peak_week['requests'])} requests.
- Weeks with no requests: {len(zero_weeks)}, the last in {zero_weeks['week_start'].max():%B}.
- Admin-entered: {admin_n} of {total} requests ({pct(admin_n, total)}). Included in demand,
  excluded from wait and lead-time figures.
"""
)

# 4 ─────────────────────────────────────────────────────────────────────────
st.header("4. Room usage")
figure(f"Figure 2. Booked hours by weekday and hour, SGT ({booked_hours} hours)")
days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
grid = heat.pivot(index="hour", columns="weekday_name", values="booked_hours")[days]
steps = len(HEAT) - 1
fig = go.Figure(
    go.Heatmap(
        z=grid.where(grid > 0).values,  # never-booked slots stay blank
        x=days,
        y=[f"{h:02d}:00" for h in grid.index],
        colorscale=[[i / steps, c] for i, c in enumerate(HEAT)],
        xgap=2,
        ygap=2,
        hoverongaps=False,
        hovertemplate="%{x} %{y}: %{z} hours booked<extra></extra>",
        colorbar=dict(title=dict(text="Hours"), thickness=10, len=0.5),
    )
)
fig.update_yaxes(autorange="reversed", showgrid=False)
fig.update_xaxes(side="top", showgrid=False)
show(fig, grid.reset_index().rename(columns={"hour": "Hour"}), 620)
st.caption("All approved sessions in the period, upcoming included. A partial hour counts as a full hour. Blank: never booked.")

figure(f"Figure 3. Evening occupancy by weekday, {occ_start} – {occ_end}")
fig = single_series_bars(
    occ["weekday_name"],
    occ["occupancy_pct"],
    "%{x}: %{y:.1f}% of evening hours booked",
    colors=[ACCENT if d == busiest else MUTED for d in occ["weekday_name"]],
    labels=[f"{num(v)}%" if d in (busiest, quietest) else None for d, v in occ_by_day.items()],
)
fig.update_yaxes(range=[0, 100], ticksuffix="%")
show(
    fig,
    occ[["weekday_name", "booked_slots", "available_slots", "occupancy_pct"]].rename(
        columns={
            "weekday_name": "Day",
            "booked_slots": "Evening hours booked",
            "available_slots": "Evening hours available",
            "occupancy_pct": "Occupancy (%)",
        }
    ),
    300,
)
st.caption("Past sessions only, 8 complete weeks, 5 evening hours per day.")

figure(f"Figure 4. Session length (n = {int(length_d['n'])})")
show(
    single_series_bars(sessions["bin"], sessions["sessions"], "%{y}: %{x} sessions", horizontal=True),
    sessions[["bin", "sessions"]].rename(columns={"bin": "Length", "sessions": "Sessions"}),
    260,
)
contiguous = unbooked_hours == list(range(unbooked_hours[0], unbooked_hours[-1] + 1)) if unbooked_hours else False
hours_label = (
    f"{unbooked_hours[0]:02d}:00–{unbooked_hours[-1]:02d}:59"
    if contiguous
    else ", ".join(f"{h:02d}:00" for h in unbooked_hours) or "no hour"
)
st.markdown(
    f"""
- {num(evening_share)}% of booked hours fall in 19:00–24:00. Peak cell: {DAY[peak_cell['weekday_name']]}
  {int(peak_cell['hour']):02d}:00, {int(peak_cell['booked_hours'])} hours.
- No bookings on any day in {hours_label}.
- Evening occupancy over the last 8 weeks: {num(occ_overall)}% overall, highest on {DAY[busiest]}
  ({num(occ_by_day[busiest])}%), lowest on {DAY[quietest]} ({num(occ_by_day[quietest])}%).
- Session length: median {num(length_d['median'])} h, IQR {num(length_d['p25'])}–{num(length_d['p75'])} h,
  max {num(length_d['max'])} h. {int(dq.loc[4, 'affected'])} sessions exceed 6 h.
- {int(dq.loc[6, 'affected'])} approved sessions were displaced by a later overlapping approval.
"""
)

# 5 ─────────────────────────────────────────────────────────────────────────
st.header("5. Booking behaviour")
figure(f"Figure 5. Lead time, public requests (n = {int(lead_d['n'])})")
show(
    single_series_bars(lead["bin"], lead["requests"], "%{y}: %{x} requests", horizontal=True),
    lead[["bin", "requests"]].rename(columns={"bin": "Lead time", "requests": "Requests"}),
    280,
)
figure("Table 3. Request type, approved requests")
type_rows = [
    [label.capitalize(), int(r["requests"]), pct(r["requests"], approved_requests), int(r["sessions"])]
    for label, r in types.iterrows()
]
st.markdown(md_table(type_rows, ["Type", "Requests", "Share", "Sessions"]))
st.caption("Custom: several hand-picked dates. Pattern: a weekly repeat.")
st.markdown(
    f"""
- Lead time: median {num(lead_d['median'])} days, IQR {num(lead_d['p25'])}–{num(lead_d['p75'])} days,
  90th percentile {num(lead_d['p90'])} days.
- {lead_under_day} of {int(lead_d['n'])} public requests ({pct(lead_under_day, lead_d['n'])}) were
  submitted less than a day before the first session.
- Multi-date requests: {int(recurring['requests'].sum())} of {approved_requests}
  ({pct(recurring['requests'].sum(), approved_requests)}), covering {int(recurring['sessions'].sum())} sessions.
"""
)

# 6 ─────────────────────────────────────────────────────────────────────────
st.header("6. Approval process")
figure(f"Figure 6. Estimated approval wait by submission window (n = {public_n})")
order = windows.index.tolist()
fig = go.Figure()
bins = wait[["bin_order", "wait_bin"]].drop_duplicates().sort_values("bin_order")
for color, (_, b) in zip(RAMP, bins.iterrows()):
    rows = wait[wait["wait_bin"] == b.wait_bin].set_index("submitted_window").loc[order]
    fig.add_bar(
        y=order,
        x=100 * rows["requests"] / rows["window_requests"],
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
        x=0,
        y=w,
        xanchor="left",
        yanchor="bottom",
        yshift=24,
        showarrow=False,
        text=f"<b>{w}</b>  n = {int(s['n'])}",
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

figure("Table 4. Approval wait by submission window (est.)")
st.markdown(
    md_table(
        [
            [w, int(s["n"]), f"{num(s['median'])} h", pct(s["under_1h"], s["n"]), pct(s["over_24h"], s["n"])]
            for w, s in windows.iterrows()
        ],
        ["Window", "n", "Median wait", "Within 1 h", "Over 24 h"],
    )
)
slowest = windows.index[-1]
st.markdown(
    f"""
- Approval wait is right-skewed: median {num(wait_d['median'])} h, p75 {num(wait_d['p75'])} h,
  p90 {num(wait_d['p90'])} h, max {num(wait_d['max'])} h.
- Highest median wait by window: {slowest.lower()} ({num(windows.loc[slowest, 'median'])} h,
  n = {int(windows.loc[slowest, 'n'])}). Weekend submissions: {num(windows.loc['Weekend', 'median'])} h.
- Approved less than 24 h before the first session: {under24} of {public_n}
  ({num(kpi['Under 24h notice'])}%). {under24 - late_n} of those {under24} were submitted less than 48 h ahead.
- Restricted to requests submitted at least 48 h ahead: {late_n} of {planned_n}
  ({num(kpi['Avoidable late notice'])}%) still received under 24 h notice.
- {int(dq.loc[2, 'affected'])} requests show an approval time after the first session started (section 7).
"""
)

# 7 ─────────────────────────────────────────────────────────────────────────
st.header("7. Data quality and instrumentation")
figure("Table 5. Data-quality checks")
impact = {
    1: ("Excluded from wait and lead-time metrics; identified by a heuristic.", "Exact from 28 Oct (event log)"),
    2: ("Inflate the wait and notice tails. Likely post-session edits or retroactive approvals.", "Unverified"),
    3: ("Produce a negative lead time.", "Included"),
    4: ("Weight the heatmap; may include entry errors.", "Unverified"),
    5: ("22:00–06:00 sessions in July; possibly AM/PM entry errors.", "Unverified"),
    6: ("Approving an overlapping request replaces the earlier approval.", "Logged as `bumped` from 28 Oct"),
    7: ("None pending at snapshot time.", "–"),
}
st.markdown(
    md_table(
        [[r["check_name"], f"{int(r['affected'])} {r['unit'].rstrip('s') if r['affected'] == 1 else r['unit']}", *impact.get(i, ("", ""))] for i, r in dq.iterrows()],
        ["Check", "Affected", "Impact", "Status"],
    )
)

figure("Table 6. Gaps in the source data, and instrumentation added 28 Oct 2026")
st.markdown(
    md_table(
        [
            ["No approval timestamp", "Wait and notice are estimates", "`booking_events`: trigger on `bookings` logs each status change with the wait at decision time"],
            ["Declined requests are hard-deleted", "Decline rate cannot be measured", "`booking_events` logs `declined` before the row is gone"],
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
st.markdown(
    md_table(
        [
            [
                "1",
                "A minority of planned-ahead requests are approved late.",
                f"{late_n} of {planned_n} ({num(kpi['Avoidable late notice'])}%)",
                "Remind admins when a request is pending and its first session is < 48 h away.",
                "Avoidable late notice, exact from the event log",
            ],
            [
                "2",
                "Late-night submissions wait longest.",
                f"Median {num(windows.loc[slowest, 'median'])} h, n = {int(windows.loc[slowest, 'n'])}",
                "None. Consistent with admin availability overnight.",
                "–",
            ],
            [
                "3",
                f"Demand has doubled; {DAY[busiest]} evenings are the most occupied.",
                f"{recent_rate / july_rate:.1f}× July; {DAY[busiest]} {num(occ_by_day[busiest])}% vs {num(occ_overall)}% all evenings",
                f"Monitor {DAY[busiest]} occupancy and displaced sessions monthly.",
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
- Each CSV comes from the SQL file with the same number. The text, tables and charts here are
  computed from those CSVs at load time.
- Sample sizes are small (n = {public_n} public requests), so the report uses medians and
  percentiles, not means. No significance testing.
- The repo holds aggregate counts only: no names, booking titles, notes or row-level records.
"""
)

footer = f"Snapshot {SNAPSHOT}. Next release {NEXT_RELEASE}."
if REPO_URL:
    footer += f" [Source and SQL]({REPO_URL})."
st.caption(footer)

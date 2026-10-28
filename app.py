"""Band room bookings: what six months of booking data says.

Every number on this page is computed from the aggregate CSVs in data/, which the
SQL in sql/ produced from the live booking database. No row-level data, names or
booking titles are in this repo, so refreshing the CSVs refreshes the whole page,
prose included.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).parent / "data"
SNAPSHOT_LABEL = "28 October 2026"
REPO_URL = ""  # set once the repo is on GitHub

st.set_page_config(page_title="Band room bookings", layout="centered")


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


def num(x: float) -> str:
    """62.5 -> '62.5', 20.0 -> '20'."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


complete = weekly[~weekly["partial_week"]]
recent_rate = complete["requests"].tail(4).mean()
july_rate = complete.loc[complete["week_start"].dt.month == 7, "requests"].mean()
admin_entered = int(weekly["likely_admin_entered"].sum())
total_requests = int(kpi["Requests"])

late_count = int(kpi["Avoidable late notice (count)"])
late_share = kpi["Avoidable late notice"]
planned_ahead = round(late_count / (late_share / 100))

occ_overall = 100 * occ["booked_slots"].sum() / occ["available_slots"].sum()
occ_by_day = occ.set_index("weekday_name")["occupancy_pct"]
busiest_day, quietest_day = occ_by_day.idxmax(), occ_by_day.idxmin()
DAY_NAMES = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
busiest_name, quietest_name = DAY_NAMES[busiest_day], DAY_NAMES[quietest_day]

window_stats = wait.groupby("submitted_window", sort=False)[["window_median_hours", "window_requests"]].first()
lead_under_day = 100 * lead.loc[lead["bin_order"] == 1, "requests"].sum() / lead["requests"].sum()
two_hours_or_less = 100 * sessions.loc[sessions["bin_order"] <= 2, "sessions"].sum() / sessions["sessions"].sum()

types = mix[mix["dimension"] == "Type"].set_index("label")
approved_requests = int(types["requests"].sum())
recurring = types.drop(index="one-off", errors="ignore")


# ── Chart helpers ────────────────────────────────────────────────────────────
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
    with st.expander("See the numbers"):
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


# ── Page ─────────────────────────────────────────────────────────────────────
st.title("Band room bookings")
st.caption(f"What six months of booking data says about how the room gets used. Data as of {SNAPSHOT_LABEL}.")

st.write(
    f"I built and run the booking system for my hall's band room. Bands request a slot on the "
    f"site and an admin approves it. In October I pulled the full booking history "
    f"({total_requests} requests since late April) to answer two questions: when is the room "
    f"actually in demand, and how long do people wait to hear back?"
)

st.subheader("The short version")
st.markdown(
    f"""
- **Demand has roughly doubled.** About {recent_rate:.0f} requests a week over the last month,
  up from {num(july_rate)} in July.
- **It's an evening room.** {num(kpi['Evening share of booked hours'])}% of booked hours fall
  between 7pm and midnight. Over the last eight weeks, {busiest_name} evenings were
  {num(occ_by_day[busiest_day])}% booked.
- **Most approvals are fast, a few are very slow.** The median wait is
  {num(kpi['Median approval wait'])} hours, but one request in ten waits
  {num(kpi['P90 approval wait'])} hours or more.
- **The slow ones are worth fixing.** {late_count} of the {planned_ahead} people who booked two
  or more days ahead still heard back less than a day before their session. A targeted reminder
  would catch those without changing anything else.
"""
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Requests", total_requests, help="Every request since launch, any outcome")
c2.metric("Median lead time", f"{num(kpi['Median lead time'])} days", help="Request to first session")
c3.metric("Median wait", f"{num(kpi['Median approval wait'])} h", help="Estimated; see the method notes")
c4.metric("Avoidable late notice", f"{num(late_share)}%", help=f"{late_count} of {planned_ahead} requests booked 2+ days ahead")

# Demand
st.header("Demand is growing")
st.markdown("#### Requests per week")
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
    name="4-week average",
    mode="lines",
    line=dict(color=TREND, width=2),
    hovertemplate="4-week average: %{y:.1f}<extra></extra>",
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
            "likely_admin_entered": "Entered by admins",
            "partial_week": "Week not over",
        }
    ),
    320,
)
st.write(
    f"Each bar counts the requests submitted that week. The orange line is a four-week average, "
    f"and the grey bar is the current week, which isn't over yet. {admin_entered} of the "
    f"{total_requests} requests were entered by admins on someone's behalf rather than through the "
    f"site; they count here, but not in the wait and lead-time figures below."
)

# When
st.header("When the room is used")
st.markdown("#### Hours booked, by day and time")
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
st.write(
    "Darker squares mean more hours booked across the whole period, upcoming sessions included. "
    "Blank squares were never booked. Weekday evenings from 7pm carry most of the use, and "
    "Wednesday stands out."
)

st.markdown("#### How full evenings get")
labels = [f"{num(v)}%" if d in (busiest_day, quietest_day) else None for d, v in occ_by_day.items()]
fig = single_series_bars(
    occ["weekday_name"],
    occ["occupancy_pct"],
    "%{x}: %{y:.1f}% of evening hours booked",
    colors=[ACCENT if d == busiest_day else MUTED for d in occ["weekday_name"]],
    labels=labels,
)
fig.update_yaxes(range=[0, 100], ticksuffix="%")
show(
    fig,
    occ[["weekday_name", "booked_slots", "available_slots", "occupancy_pct"]].rename(
        columns={
            "weekday_name": "Day",
            "booked_slots": "Evening hours booked",
            "available_slots": "Evening hours available",
            "occupancy_pct": "Booked (%)",
        }
    ),
    300,
)
start = pd.to_datetime(occ["window_start"].iloc[0]).strftime("%d %b")
end = pd.to_datetime(occ["window_end"].iloc[0]).strftime("%d %b")
st.write(
    f"Share of the 7pm to midnight hours that were actually used, {start} to {end} (past sessions "
    f"only). Even the busiest night has room: {busiest_name} evenings were "
    f"{num(occ_by_day[busiest_day])}% booked and {quietest_name} evenings "
    f"{num(occ_by_day[quietest_day])}%. Across the week, {occ_overall:.0f}% of evening hours were "
    f"used. Clashes still happen: {int(kpi['Bumped bookings'])} approved bookings were later "
    f"replaced by an overlapping one."
)

# How people book
st.header("How people book")
st.markdown("#### How far ahead people ask")
show(
    single_series_bars(lead["bin"], lead["requests"], "%{y}: %{x} requests", horizontal=True),
    lead[["bin", "requests"]].rename(columns={"bin": "Asked ahead by", "requests": "Requests"}),
    280,
)
st.write(
    f"Request to first session, for requests made through the site. The median is "
    f"{num(kpi['Median lead time'])} days, and {lead_under_day:.0f}% ask less than a day ahead."
)

st.markdown("#### How long sessions run")
show(
    single_series_bars(sessions["bin"], sessions["sessions"], "%{y}: %{x} sessions", horizontal=True),
    sessions[["bin", "sessions"]].rename(columns={"bin": "Length", "sessions": "Sessions"}),
    280,
)
st.write(
    f"Approved sessions by length. The median is {num(sessions['median_hours'].iloc[0])} hours, "
    f"and {two_hours_or_less:.0f}% run two hours or less."
)

t1, t2, t3 = st.columns(3)
t1.metric("One-off requests", f"{100 * types.loc['one-off', 'requests'] / approved_requests:.0f}%")
t2.metric("Recurring requests", int(recurring["requests"].sum()), help=f"Covering {int(recurring['sessions'].sum())} sessions")
t3.metric("Bumped bookings", int(kpi["Bumped bookings"]), help="Approved, then replaced by an overlapping approval")

# Approvals
st.header("How long approvals take")
st.write(
    "The database has no approval timestamp, so I estimated it from when each booking was last "
    "updated. An edit made after approval makes a wait look longer than it was, so these are "
    "upper-end estimates."
)

st.markdown("#### The first number I looked at was misleading")
m1, m2 = st.columns(2)
m1.metric("Under 24 hours' notice", f"{num(kpi['Under 24h notice'])}%", help="All public requests")
m2.metric("Avoidable late notice", f"{num(late_share)}%", help=f"{late_count} of {planned_ahead} requests booked 2+ days ahead")
st.write(
    f"A third of bookers heard back less than 24 hours before their session. But many of them "
    f"booked the same day or the day before, so a late answer couldn't be avoided. Counting only "
    f"people who booked at least two days ahead, {late_count} of {planned_ahead} still got under "
    f"24 hours' notice. That's the number worth fixing."
)

st.markdown("#### Wait by when the request was sent")
order = window_stats.sort_values("window_median_hours").index.tolist()
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
# Each window's name and median sit above its bar rather than beside it, so the bars
# keep the full width on a phone.
for w, s in window_stats.loc[order].iterrows():
    fig.add_annotation(
        x=0,
        y=w,
        xanchor="left",
        yanchor="bottom",
        yshift=24,
        showarrow=False,
        text=f"<b>{w}</b>  median {num(s.window_median_hours)}h · {int(s.window_requests)} requests",
    )
fig.update_layout(barmode="stack", bargap=0.6, legend=dict(orientation="h", x=0, y=1.0, yanchor="bottom", traceorder="normal"))
fig.update_xaxes(range=[0, 100], ticksuffix="%", showgrid=False)
fig.update_yaxes(autorange="reversed", showticklabels=False)
show(
    fig,
    wait[["submitted_window", "wait_bin", "requests", "window_median_hours"]].rename(
        columns={
            "submitted_window": "Sent",
            "wait_bin": "Waited",
            "requests": "Requests",
            "window_median_hours": "Median wait for this window (h)",
        }
    ),
    340,
    top=64,
)
weekend = window_stats.loc["Weekend", "window_median_hours"]
night = window_stats.loc["Weekday late night", "window_median_hours"]
day = window_stats.loc["Weekday daytime", "window_median_hours"]
st.write(
    f"My first guess was that weekend requests wait longest. They don't: the median weekend wait is "
    f"{num(weekend)} hours. Requests sent between 11pm and 7am wait longest (median {num(night)} "
    f"hours), mostly because admins are asleep. Requests sent during the day are usually approved "
    f"within {day * 60:.0f} minutes. Weekend means Friday 6pm to Sunday."
)

# Recommendation
st.header("What I'd change")
st.write(
    f"The process works for most requests. The problem is a handful that get forgotten and are "
    f"approved hours before the session, occasionally after it ({int(kpi['Approved after session start'])} "
    f"cases). So I'm recommending one narrow change to the committee: if a request is still pending "
    f"and its session is less than 48 hours away, the admin chat gets a reminder. I'll judge it on "
    f"avoidable late notice, {num(late_share)}% today, once the new event log has a few weeks of "
    f"exact timings."
)

# Method
st.header("Method and caveats")
st.markdown(
    f"""
- **Data:** every booking request from late April to {SNAPSHOT_LABEL}, queried with SQL and
  aggregated before export. A request covering several dates counts once.
- **Approval wait is an estimate**, as explained above. Exact timings start on 28 October, when I
  added an event log that records each approval and decline as it happens.
- **{admin_entered} requests were entered by admins** directly. They're excluded from the wait and
  lead-time figures.
- **Heatmap and evening share** include upcoming approved sessions, and a partial hour counts as a
  full one. Evening occupancy uses past sessions only.
- **Small sample:** {int(kpi['Public requests approved'])} approved requests came through the site,
  so I report medians and percentiles rather than averages.
- **Declined requests are deleted by the app**, so they don't appear here. The new log records them
  from now on.
- **Privacy:** this page and its repo hold aggregate counts only. No names, booking titles or notes.
"""
)

footer = "Built with SQL, pandas, Plotly and Streamlit."
if REPO_URL:
    footer += f" [Source and queries]({REPO_URL})."
st.caption(footer)

"""Edge cases: the report must render, and phrase itself correctly, on data shapes the
real snapshot does not have yet. Each case copies data/ to a temporary folder, reshapes
it, and renders every period."""

import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

REAL = Path(__file__).parent / "data"
PERIODS = ["All time", "Last 8 weeks", "Last 4 weeks"]
QUIET = "Last 4 weeks"


def variant(mutate) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="report-edge-"))
    for f in REAL.iterdir():
        shutil.copy(f, folder / f.name)
    mutate(folder)
    return folder


def edit(folder: Path, name: str, change) -> None:
    path = folder / f"{name}.csv"
    frame = pd.read_csv(path)
    change(frame).to_csv(path, index=False)


def render(folder: Path, period: str) -> str:
    os.environ["REPORT_DATA_DIR"] = str(folder)
    at = AppTest.from_file("app.py")
    at.session_state["period"] = period
    at = at.run(timeout=60)
    assert not at.exception, (folder.name, period, at.exception)
    return "\n".join(m.value for m in at.markdown)


def quiet_period(folder: Path) -> None:
    """A holiday: nothing requested or held in the last four weeks."""
    q = lambda f: f["period"] == QUIET  # noqa: E731
    counts = ["requests", "approved", "public_approved", "admin_entered", "grouped_approved",
              "under_24h", "booked_48h_ahead", "avoidable_late", "approved_after_start"]

    def kpis(f):
        f.loc[q(f), counts] = 0
        return f

    def zero(column, *blank):
        def change(f):
            f.loc[q(f), column] = 0
            for col in blank:
                f[col] = f[col].astype("float64")
                f.loc[q(f), col] = float("nan")
            return f
        return change

    edit(folder, "01_kpis", kpis)
    edit(folder, "03_heatmap", zero("booked_hours"))
    edit(folder, "04_lead_time", zero("requests"))
    edit(folder, "05_wait_by_window", lambda f: zero("window_requests", "window_median_hours")(zero("requests")(f)))
    edit(folder, "06_request_mix", lambda f: f[~q(f)])
    edit(folder, "08_session_length", zero("sessions", "median_hours"))
    edit(folder, "09_distributions", lambda f: f[~q(f)])


def no_late_approvals(folder: Path) -> None:
    """Every request answered in good time."""
    def kpis(f):
        f[["under_24h", "avoidable_late", "approved_after_start"]] = 0
        return f
    edit(folder, "01_kpis", kpis)


def all_evenings_tied(folder: Path) -> None:
    """Every evening slot in use equally often, so 'hardest' is a 35-way tie."""
    def heat(f):
        evening = f["hour"] >= 19
        f.loc[evening, "booked_hours"] = (f.loc[evening, "weeks"] // 2).astype(int)
        return f
    edit(folder, "03_heatmap", heat)


def flat_demand(folder: Path) -> None:
    """Demand that did not grow: the 'doubled' story must not appear."""
    def weekly(f):
        f["requests"] = 5
        return f
    edit(folder, "02_weekly_demand", weekly)


def test_quiet_period() -> None:
    text = render(variant(quiet_period), QUIET)
    assert "No sessions were held in this period" in text
    assert "No requests were made through the site in this period" in text
    for period in PERIODS[:2]:
        render(variant(quiet_period), period)


def test_no_late_approvals() -> None:
    folder = variant(no_late_approvals)
    # Counts come from the data, so the test holds for every snapshot.
    kpis = pd.read_csv(folder / "01_kpis.csv").set_index("period").loc["All time"]
    text = render(folder, "All time")
    assert f"None of the {kpis.public_approved} requests was approved less than a day before its first session." in text
    assert f"Every one of the {kpis.booked_48h_ahead} requests submitted at least two days ahead" in text
    assert "still got" not in text
    assert "Planned-ahead requests are all approved in good time." in text


def test_all_evenings_tied() -> None:
    text = render(variant(all_evenings_tied), "Last 8 weeks")
    assert "35 evening times tied as the hardest to book" in text
    assert "| Mon | – | All evening | – |" in text


def test_days_before_real_use_not_counted() -> None:
    """29-30 Jun sit in the first week but before real use, so they are not free hours."""
    used = pd.read_csv(REAL / "11_evening_by_week.csv")
    first = used.loc[used["week_start"] < "2026-07-27", "evening_slots_in_use"].sum()
    text = render(REAL, "All time")
    assert f"fell from {100 - 100 * first / 130:.0f}% in the four weeks to 26 Jul" in text


def test_flat_demand() -> None:
    text = render(variant(flat_demand), "All time")
    assert "doubled" not in text
    assert "held roughly steady" in text


if __name__ == "__main__":
    for name, case in list(globals().items()):
        if name.startswith("test_"):
            case()
            print("ok", name)

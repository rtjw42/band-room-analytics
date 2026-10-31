"""Smoke test: the report renders top to bottom for every period and heatmap view."""
from streamlit.testing.v1 import AppTest

PERIODS = ["All time", "Last 8 weeks", "Last 4 weeks"]
VIEWS = ["Hours in use", "Share of weeks in use"]


def render(period: str, view: str) -> AppTest:
    at = AppTest.from_file("app.py")
    at.session_state["period"] = period
    at.session_state["heat_view"] = view
    return at.run(timeout=60)


def test_app_renders():
    for period in PERIODS:
        for view in VIEWS:
            at = render(period, view)
            assert not at.exception, (period, view, at.exception)
            assert at.title[0].value == "Band room booking report"
            assert [h.value.split(".")[0] for h in at.header] == [str(i) for i in range(1, 11)]
            assert len(at.get("plotly_chart")) == 7


if __name__ == "__main__":
    test_app_renders()
    print("ok")

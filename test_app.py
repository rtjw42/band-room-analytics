"""Smoke test: the report renders top to bottom without an exception."""
from streamlit.testing.v1 import AppTest


def test_app_renders():
    at = AppTest.from_file("app.py").run(timeout=60)
    assert not at.exception
    assert at.title[0].value == "Band room booking report"
    assert [h.value.split(".")[0] for h in at.header] == [str(i) for i in range(1, 10)]


if __name__ == "__main__":
    test_app_renders()
    print("ok")

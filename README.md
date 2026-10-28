# Band room bookings

An analysis of six months of data from the band-room booking system I built and run for my
university hall. Bands request a slot online and an admin approves it.

**Live dashboard:** _link coming once deployed_
**The booking app itself:** [rtjw42/ehbr-public](https://github.com/rtjw42/ehbr-public)

## The questions

1. When is the room actually in demand?
2. How long do people wait for an approval, and when does that wait cause problems?

## What I found (data as of 28 October 2026)

- **Demand roughly doubled** between July and October, from about 4.5 to 10 requests a week.
- **It's an evening room.** 69% of booked hours fall between 7pm and midnight. Wednesday
  evenings were 62.5% booked over the last eight weeks; Monday evenings 20%.
- **Most approvals are fast, a few are very slow.** The median wait is 1.5 hours; the slowest
  10% wait 46.6 hours or more.
- **The obvious metric was misleading.** 33% of bookers heard back less than 24 hours before
  their session, but most of them had booked at the last minute. Counting only people who
  booked two or more days ahead, 5 of 43 (11.6%) still heard back late. That is the number
  worth fixing.
- **My first hypothesis was wrong.** I expected weekend requests to wait longest (median
  3.3 hours). Requests sent between 11pm and 7am do (median 14.1 hours).

The recommendation, and how it will be measured, is in the dashboard.

## How it's built

```
Postgres (Supabase)  →  SQL in sql/  →  aggregate CSVs in data/  →  pandas + Plotly  →  Streamlit
```

- `sql/` holds the query behind each CSV.
- `data/` is one dated snapshot of aggregates.
- `app.py` is the dashboard. Every number in its text is computed from `data/`, so a new
  snapshot updates the charts and the prose together.

## Privacy

This repo holds aggregate counts only: no names, booking titles, notes or row-level records.

## Caveats

The booking database has no approval timestamp, so approval wait is estimated from when each
booking was last updated, which can overstate a wait. Exact timings are being collected from
28 October 2026 by a new event log. The sample is small (70 approved requests made through the
site), so the analysis uses medians and percentiles rather than averages. Full notes are in the
dashboard's "Method and caveats" section.

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Smoke test: `.venv/bin/python test_app.py`

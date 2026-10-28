# Band room booking report

Descriptive analysis of the booking database behind a university hall's band-room booking
system: demand, room usage, booking behaviour, approval latency and data quality.

- **Live report:** _link added once deployed_
- **Booking system source:** [rtjw42/ehbr-public](https://github.com/rtjw42/ehbr-public)

## Scope

| | |
|---|---|
| Source | Booking database (Postgres, Supabase): `bookings`, `booking_groups` |
| Requests | Submitted 30 Apr – 25 Oct 2026 (the last complete week before the snapshot) |
| Sessions | Held 29 Jun – 25 Oct 2026; every approved session falls in this range |
| Snapshot | 28 Oct 2026, SGT |
| Size | 105 requests; 67 public requests with a measurable wait; 99 approved sessions |
| Unit | Request (`coalesce(group_id, id)`) unless stated |
| Periods | All time, last 8 weeks, last 4 weeks, selectable in the report |

## Key results (all time unless stated)

| Metric | Value |
|---|---|
| Requests per week, last 4 complete weeks vs July | 10 vs 4.5 |
| Hour slots in use falling in 19:00–24:00 | 69.2% |
| Evening occupancy, last 8 weeks (Wednesday / all days) | 62.5% / 38.9% |
| Lead time, median (IQR) | 2.9 days (1.2–4.2) |
| Approval wait, median / p90 (estimated) | 1.7 h / 46.6 h |
| Median wait by submission window: daytime / weekend / late night | 0.3 h / 3.3 h / 10.7 h |
| Approved < 24 h before first session (estimated) | 32.8% (22 of 67) |
| Same, among requests made ≥ 48 h ahead | 11.9% (5 of 42) |

July was the first month of regular use, so part of the rise since then is ramp-up after launch.

## Repository layout

```
sql/        one query per dataset (Postgres)
data/       aggregate CSVs produced by those queries, one snapshot
app.py      the report (Streamlit, pandas, Plotly); every figure is computed from data/
.streamlit/ theme matching the booking site's design tokens
```

`NN_name.sql` produces `NN_name.csv`. Most datasets carry a `period` column with one block of
rows per period; the report's period filter selects rows and recomputes nothing. Replacing
`data/` with a new snapshot updates every table, chart and sentence.

## Data quality

- **No approval timestamp** in the source table. Approval time is estimated as
  `max(updated_at)`, which overstates waits for bookings edited after approval.
- **Declined requests are hard-deleted**, so decline rate is not measurable from this snapshot.
- **Admin-entered requests** (31) are identified by `updated_at = created_at` and excluded from
  wait and lead-time metrics.
- **All 7 displaced sessions predate regular use** (scheduled in May–June); none since.
- Instrumentation added on 28 Oct 2026 (an event log of status changes and hourly booking-form
  step counts) removes the first two gaps from the next snapshot onward.

The full list, with counts, is in section 7 of the report.

## Privacy

Aggregate counts only. No names, booking titles, notes, identifiers or row-level records.

## Running locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Smoke test (every period and heatmap view): `.venv/bin/python test_app.py`

# Band room booking report

Descriptive analysis of the booking database behind a university hall's band-room booking
system: demand, room usage and availability, booking behaviour, approval latency and data
quality. Includes an animated chart of how evening availability changed, four weeks at a time.

- **Live report:** [band-room-report.streamlit.app](https://band-room-report.streamlit.app/)
- **Booking system source:** [rtjw42/ehbr-public](https://github.com/rtjw42/ehbr-public)

<!-- generated:start -->
## Scope

| | |
|---|---|
| Source | Booking database (Postgres, Supabase): `bookings`, `booking_groups` |
| Requests | Submitted 30 Apr 2026 – 1 Nov 2026 (the last complete week before the snapshot) |
| Sessions | Held 29 Jun 2026 – 1 Nov 2026; every approved session falls in this range |
| Snapshot | 2 Nov 2026, SGT |
| Size | 112 requests; 74 public requests with a measurable wait; 109 approved sessions |
| Unit | Request (`coalesce(group_id, id)`) unless stated |
| Periods | All time, last 8 weeks, last 4 weeks, selectable in the report |

## Key results (all time unless stated)

| Metric | Value |
|---|---|
| Requests per week, last 4 complete weeks vs July | 9.5 vs 4.5 |
| Hour slots in use falling in 19:00–24:00 | 69% |
| Evening occupancy, last 8 weeks (fullest day, Friday / all days) | 60% / 41.8% |
| Hardest evening slots, last 8 weeks | Friday 21:00 and Friday 22:00: free 1 of 8 weeks |
| Lead time, median (IQR) | 2.9 days (1.2–4.2) |
| Approval wait, median / p90 (estimated) | 1.9 h / 48.7 h |
| Median wait by submission window: daytime / weekend / late night | 0.3 h / 2.4 h / 14.1 h |
| Approved < 24 h before first session (estimated) | 33.8% (25 of 74) |
| Same, among requests made ≥ 48 h ahead | 10.9% (5 of 46) |

July was the first month of regular use, so part of the rise since then is ramp-up after launch.
<!-- generated:end -->

## Repository layout

```
sql/        one query per dataset (Postgres)
data/       aggregate CSVs produced by those queries, one snapshot
app.py      the report (Streamlit, pandas, Plotly); every figure is computed from data/
.streamlit/ theme matching the booking site's design tokens
```

`NN_name.sql` produces `NN_name.csv`. The Scope and Key results tables above are generated
from `data/` by `readme_results.py`, so they always match the snapshot. Most datasets carry a `period` column with one block of
rows per period; the report's period filter selects rows and recomputes nothing. Replacing
`data/` with a new snapshot updates every table, chart and sentence.

## Data quality

- **No approval timestamp** in the source table. Approval time is estimated as
  `max(updated_at)`, which overstates waits for bookings edited after approval.
- **Declined requests are hard-deleted**, so decline rate is not measurable from this snapshot.
- **Admin-entered requests** are identified by `updated_at = created_at` and excluded from
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

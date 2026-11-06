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
| Requests | Submitted 18 Jun 2026 – 1 Nov 2026 (the last complete week before the snapshot) |
| Sessions | Held 1 Jul 2026 – 1 Nov 2026; every approved session falls in this range |
| Snapshot | 6 Nov 2026, SGT |
| Size | 105 requests; 73 public requests with a measurable wait; 109 approved sessions |
| Unit | Request (`coalesce(group_id, id)`) unless stated |
| Periods | All time, last 8 weeks, last 4 weeks, selectable in the report |

## Key results (all time unless stated)

| Metric | Value |
|---|---|
| Requests per week, last 4 complete weeks vs July | 9.5 vs 4.5 |
| Hours in use falling in 19:00–24:00 | 69% |
| Evening hours in use, last 8 weeks (fullest day, Friday / all days) | 60% / 41.8% |
| Hardest evening times, last 8 weeks | Friday 21:00 and Friday 22:00: free 1 of 8 weeks |
| Days ahead (lead time), median (IQR) | 2.9 days (1.2–4.2) |
| Approval wait, median / p90 (estimated) | 1.7 h / 46.5 h |
| Median wait by when the request was sent: daytime / weekend / late night | 0.3 h / 2.2 h / 14.1 h |
| Approved < 24 h before first session (estimated) | 32.9% (24 of 73) |
| Made early, approved late (requests made ≥ 48 h ahead) | 11.1% (5 of 45) |

Real use began on 1 Jul 2026, so part of the rise since then is the room settling in after launch.
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
  `min(updated_at)` across a request's rows, which overstates waits for single-session
  requests edited after approval. The estimate was checked on 4 Nov 2026 against the exact
  event log and the Telegram request pings; section 8 of the report has the outcome.
- **Declined requests are hard-deleted**, so decline rate is not measurable from this snapshot.
- **Admin-entered requests** are identified by `updated_at = created_at` on any row and
  excluded from wait and lead-time metrics.
- **Real use began on 1 Jul 2026.** Before that the site was in development, and the last few
  weeks of June were early user testing, so bookings for sessions before 1 Jul are left out of
  every figure.
- Instrumentation added on 28 Oct 2026 (an event log of status changes and hourly booking-form
  step counts) removes the first two gaps from the next snapshot onward.

The full list, with counts, is in section 8 of the report.

## Privacy

Aggregate counts only. No names, booking titles, notes, identifiers or row-level records.

## Running locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Smoke test (every period and heatmap view): `.venv/bin/python test_app.py`

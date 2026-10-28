# Band room booking report

Descriptive analysis of the booking database behind a university hall's band-room booking
system: demand, room usage, booking behaviour, approval latency and data quality.

- **Live report:** _link added once deployed_
- **Booking system source:** [rtjw42/ehbr-public](https://github.com/rtjw42/ehbr-public)

## Scope

| | |
|---|---|
| Source | Booking database (Postgres, Supabase): `bookings`, `booking_groups` |
| Period | 29 Apr – 28 Oct 2026 |
| Snapshot | 28 Oct 2026, SGT |
| Size | 108 requests, 117 sessions; 70 public requests with a measurable wait |
| Unit | Request (`coalesce(group_id, id)`) unless stated |

## Key results (snapshot 28 Oct 2026)

| Metric | Value |
|---|---|
| Requests per week, last 4 complete weeks vs July | 10.0 vs 4.5 |
| Booked hours falling in 19:00–24:00 | 69.4% |
| Evening occupancy, last 8 weeks (Wednesday / all days) | 62.5% / 38.9% |
| Lead time, median (IQR) | 2.9 days (1.2–4.2) |
| Approval wait, median / p90 (estimated) | 1.5 h / 46.6 h |
| Median wait by submission window: daytime / weekend / late night | 0.3 h / 3.3 h / 14.1 h |
| Approved < 24 h before first session (estimated) | 32.9% (23 of 70) |
| Same, among requests made ≥ 48 h ahead | 11.6% (5 of 43) |

## Repository layout

```
sql/    one query per dataset (Postgres)
data/   aggregate CSVs produced by those queries, one snapshot
app.py  the report (Streamlit, pandas, Plotly); every figure is computed from data/
```

`NN_name.sql` produces `NN_name.csv`. The report's text, tables and charts are computed from
the CSVs at load time, so replacing `data/` with a new snapshot updates all of them.

## Data quality

- **No approval timestamp** in the source table. Approval time is estimated as
  `max(updated_at)`, which overstates waits for bookings edited after approval.
- **Declined requests are hard-deleted**, so decline rate is not measurable from this snapshot.
- **Admin-entered requests** (31) are identified by `updated_at = created_at` and excluded from
  wait and lead-time metrics.
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

Smoke test: `.venv/bin/python test_app.py`

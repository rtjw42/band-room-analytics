-- KPI tiles, long format (one row per metric). A request is coalesce(group_id, id):
-- a multi-date or weekly submission counts once. "Public" = approved requests that
-- were updated after insert, i.e. requested and then approved; admin-entered rows
-- are inserted already approved and never updated. Approval time is ESTIMATED as
-- max(updated_at), which an edit after approval inflates (exact data: booking_events).
with req as (
  select coalesce(group_id, id)            as rid,
         min(created_at)                   as asked,
         max(updated_at)                   as last_update,
         min(start_time)                   as first_session,
         bool_and(status = 'approved')     as approved,
         bool_and(updated_at = created_at) as admin_entered,
         bool_or(group_id is not null)     as grouped
  from public.bookings
  group by 1
),
pub as (
  select * from req where approved and not admin_entered
),
hrs as (
  select extract(isodow from s)::int as weekday, extract(hour from s)::int as hour
  from public.bookings b,
       generate_series(date_trunc('hour', b.start_time at time zone 'Asia/Singapore'),
                       (b.end_time at time zone 'Asia/Singapore') - interval '1 second',
                       interval '1 hour') s
  where b.status = 'approved'
)
select sort, metric, value, unit, note
from (values
  (1, 'Requests', (select count(*) from req)::numeric, 'requests',
      'All requests since launch, any outcome'),
  (2, 'Public requests approved', (select count(*) from pub)::numeric, 'requests',
      'Requested by a booker, then approved by an admin'),
  (3, 'Bumped bookings', (select count(*) from public.bookings where status = 'rejected')::numeric, 'sessions',
      'Approved, then displaced by an overlapping approval'),
  (4, 'Median lead time', (select round((percentile_cont(0.5) within group (order by extract(epoch from first_session - asked) / 86400))::numeric, 1) from pub), 'days',
      'Submission to first session, public requests'),
  (5, 'Median approval wait', (select round((percentile_cont(0.5) within group (order by extract(epoch from last_update - asked) / 3600))::numeric, 1) from pub), 'hours',
      'Estimate: max(updated_at) - created_at'),
  (6, 'P90 approval wait', (select round((percentile_cont(0.9) within group (order by extract(epoch from last_update - asked) / 3600))::numeric, 1) from pub), 'hours',
      'Estimate; 1 in 10 public requests waits at least this long'),
  (7, 'Under 24h notice', (select round(100.0 * count(*) filter (where first_session - last_update < interval '24 hours') / count(*), 1) from pub), 'percent',
      'Approved less than 24h before the first session; includes unavoidable last-minute bookings'),
  (8, 'Avoidable late notice', (select round(100.0 * count(*) filter (where first_session - last_update < interval '24 hours') / nullif(count(*), 0), 1) from pub where first_session - asked >= interval '48 hours'), 'percent',
      'Booked 48h+ ahead, still approved under 24h before the session'),
  (9, 'Avoidable late notice (count)', (select count(*) filter (where first_session - last_update < interval '24 hours') from pub where first_session - asked >= interval '48 hours')::numeric, 'requests',
      'Numerator of the row above'),
  (10, 'Approved after session start', (select count(*) filter (where first_session < last_update) from pub)::numeric, 'requests',
      'Estimate; may be an edit after the session rather than a late approval'),
  (11, 'Recurring share', (select round(100.0 * count(*) filter (where grouped) / count(*), 1) from req where approved), 'percent',
      'Approved requests covering more than one date'),
  (12, 'Evening share of booked hours', (select round(100.0 * count(*) filter (where hour >= 19) / count(*), 1) from hrs), 'percent',
      '19:00-24:00 SGT, approved sessions incl. upcoming')
) v(sort, metric, value, unit, note)
order by sort;

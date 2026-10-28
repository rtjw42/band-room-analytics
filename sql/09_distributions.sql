-- Distribution summaries (quartiles, p90, range) for the duration metrics, long format.
-- Request-level metrics cover public requests only (requested, then approved); admin-
-- entered requests are inserted already approved and have no meaningful wait or lead.
-- Approval time is ESTIMATED as max(updated_at); an edit after approval inflates it.
with req as (
  select min(created_at)                   as asked,
         max(updated_at)                   as last_update,
         min(start_time)                   as first_session,
         bool_and(status = 'approved')     as approved,
         bool_and(updated_at = created_at) as admin_entered
  from public.bookings
  group by coalesce(group_id, id)
),
pub as (
  select * from req where approved and not admin_entered
),
vals(sort, metric, unit, v) as (
  select 1, 'Lead time (request to first session)', 'days',
         extract(epoch from first_session - asked) / 86400 from pub
  union all
  select 2, 'Approval wait (estimated)', 'hours',
         extract(epoch from last_update - asked) / 3600 from pub
  union all
  select 3, 'Notice before first session (estimated)', 'hours',
         extract(epoch from first_session - last_update) / 3600 from pub
  union all
  select 4, 'Session length', 'hours',
         extract(epoch from end_time - start_time) / 3600
  from public.bookings where status = 'approved'
)
select sort, metric, unit, count(*) as n,
       round((percentile_cont(0.25) within group (order by v))::numeric, 1) as p25,
       round((percentile_cont(0.50) within group (order by v))::numeric, 1) as median,
       round((percentile_cont(0.75) within group (order by v))::numeric, 1) as p75,
       round((percentile_cont(0.90) within group (order by v))::numeric, 1) as p90,
       round(min(v)::numeric, 1) as min,
       round(max(v)::numeric, 1) as max
from vals
group by sort, metric, unit
order by sort;

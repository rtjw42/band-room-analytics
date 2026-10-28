-- Distribution summaries (quartiles, p90, range) for the duration metrics, per period.
-- Request-level metrics cover public requests only; admin-entered requests are
-- inserted already approved and have no meaningful wait or lead time. Approval time is
-- ESTIMATED as max(updated_at); an edit after approval inflates it.
-- Periods (all time, last 8 weeks, last 4 weeks) end at the start of the current week, SGT,
-- so every figure covers complete weeks only and no upcoming sessions. A request belongs
-- to the period it was submitted in; a session to the period it took place in.
with bounds as (
  select date_trunc('week', now() at time zone 'Asia/Singapore') as cutoff  -- start of the current week, SGT
),
periods(period_order, period, start_local, end_local) as (
  select 1, 'All time', timestamp '-infinity', cutoff from bounds
  union all select 2, 'Last 8 weeks', cutoff - interval '8 weeks', cutoff from bounds
  union all select 3, 'Last 4 weeks', cutoff - interval '4 weeks', cutoff from bounds
),
req as (
  select min(created_at)                   as asked,
         max(updated_at)                   as last_update,
         min(start_time)                   as first_session,
         bool_and(status = 'approved')     as approved,
         bool_and(updated_at = created_at) as admin_entered,
         bool_or(group_id is not null)     as grouped
  from public.bookings
  group by coalesce(group_id, id)
),
pub as (
  select p.period_order, p.period, r.*
  from periods p join req r on r.asked at time zone 'Asia/Singapore' >= p.start_local and r.asked at time zone 'Asia/Singapore' < p.end_local
  where r.approved and not r.admin_entered
),
ses as (
  select p.period_order, p.period, extract(epoch from b.end_time - b.start_time) / 3600 as hours
  from periods p
  join public.bookings b
    on b.status = 'approved'
   and b.start_time at time zone 'Asia/Singapore' >= p.start_local
   and b.start_time at time zone 'Asia/Singapore' <  p.end_local
),
vals(period_order, period, sort, metric, unit, v) as (
  select period_order, period, 1, 'Lead time (request to first session)', 'days',
         extract(epoch from first_session - asked) / 86400 from pub
  union all
  select period_order, period, 2, 'Approval wait (estimated)', 'hours',
         extract(epoch from last_update - asked) / 3600 from pub
  union all
  select period_order, period, 3, 'Notice before first session (estimated)', 'hours',
         extract(epoch from first_session - last_update) / 3600 from pub
  union all
  select period_order, period, 4, 'Session length', 'hours', hours from ses
)
select period_order, period, sort, metric, unit, count(*) as n,
       round((percentile_cont(0.25) within group (order by v))::numeric, 1) as p25,
       round((percentile_cont(0.50) within group (order by v))::numeric, 1) as median,
       round((percentile_cont(0.75) within group (order by v))::numeric, 1) as p75,
       round((percentile_cont(0.90) within group (order by v))::numeric, 1) as p90,
       round(min(v)::numeric, 1) as min,
       round(max(v)::numeric, 1) as max
from vals
group by 1, 2, 3, 4, 5
order by 1, 3;

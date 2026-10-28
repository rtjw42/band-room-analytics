-- How far ahead bookers ask, per period: public requests, submission to first session,
-- pre-binned (aggregates only). Empty bins are kept.
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
  select p.period, extract(epoch from r.first_session - r.asked) / 86400 as days
  from periods p join req r on r.asked at time zone 'Asia/Singapore' >= p.start_local and r.asked at time zone 'Asia/Singapore' < p.end_local
  where r.approved and not r.admin_entered
),
bins(bin_order, bin, lo, hi) as (
  values (1, 'Under 1 day', -1e9, 1), (2, '1-2 days', 1, 2), (3, '2-3 days', 2, 3),
         (4, '3-7 days', 3, 7), (5, '1-2 weeks', 7, 14), (6, '2+ weeks', 14, 1e9)
)
select p.period_order, p.period, bins.bin_order, bins.bin, count(pub.days) as requests
from periods p
cross join bins
left join pub on pub.period = p.period and pub.days >= bins.lo and pub.days < bins.hi
group by 1, 2, 3, 4
order by 1, 3;

-- Request mix per period: booking type (approved requests) and outcome, as
-- dimension / label / counts.
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
req2 as (
  select coalesce(b.group_id, b.id)      as rid,
         coalesce(g.kind, 'one-off')     as kind,
         min(b.created_at)               as asked,
         bool_and(b.status = 'approved') as approved,
         bool_or(b.status = 'rejected')  as bumped,
         count(*)                        as sessions
  from public.bookings b
  left join public.booking_groups g on g.id = b.group_id
  group by 1, 2
),
rp as (
  select p.period_order, p.period, r.*
  from periods p join req2 r on r.asked at time zone 'Asia/Singapore' >= p.start_local and r.asked at time zone 'Asia/Singapore' < p.end_local
)
select period_order, period, 'Type' as dimension, kind as label, count(*) as requests, sum(sessions) as sessions
from rp where approved group by 1, 2, 4
union all
select period_order, period, 'Outcome',
       case when bumped then 'Bumped' when approved then 'Approved' else 'Pending' end,
       count(*), sum(sessions)
from rp group by 1, 2, 4
order by 1, 3, 5 desc;

-- Request counts per period, one row per period.
-- Periods (all time, last 8 weeks, last 4 weeks) end at the start of the current week, SGT,
-- so every figure covers complete weeks only and no upcoming sessions. A request belongs
-- to the period it was submitted in; a session to the period it took place in.
-- "Public" = requested through the site, then approved (updated_at > created_at on some row).
-- Approval time is ESTIMATED as max(updated_at); an edit after approval inflates it.
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
rp as (
  select p.period_order, p.period, p.start_local, p.end_local, r.*
  from periods p
  left join req r on r.asked at time zone 'Asia/Singapore' >= p.start_local and r.asked at time zone 'Asia/Singapore' < p.end_local
)
select period_order, period,
       coalesce(nullif(start_local, '-infinity'), (select min(created_at at time zone 'Asia/Singapore') from public.bookings))::date as period_start,
       (end_local - interval '1 day')::date as period_end,
       count(asked)                                                                       as requests,
       count(*) filter (where approved)                                                   as approved,
       count(*) filter (where approved and not admin_entered)                             as public_approved,
       count(*) filter (where approved and admin_entered)                                 as admin_entered,
       count(*) filter (where approved and grouped)                                       as grouped_approved,
       count(*) filter (where approved and not admin_entered
                          and first_session - last_update < interval '24 hours')          as under_24h,
       count(*) filter (where approved and not admin_entered
                          and first_session - asked >= interval '48 hours')               as booked_48h_ahead,
       count(*) filter (where approved and not admin_entered
                          and first_session - asked >= interval '48 hours'
                          and first_session - last_update < interval '24 hours')          as avoidable_late,
       count(*) filter (where approved and not admin_entered and first_session < last_update) as approved_after_start
from rp
group by period_order, period, start_local, end_local
order by period_order;

-- Requests and sessions per week (Monday start, SGT), by submission time. Weeks
-- with no requests are filled with zeros so the line does not skip them.
-- likely_admin_entered: requests inserted already approved (estimate).
with r as (
  select coalesce(group_id, id)                              as rid,
         min(created_at at time zone 'Asia/Singapore')       as asked,
         count(*)                                            as sessions,
         bool_and(status = 'approved' and updated_at = created_at) as admin_entered
  from public.bookings
  group by 1
),
w as (
  select date_trunc('week', asked)::date as week_start,
         count(*)                         as requests,
         sum(sessions)                    as sessions,
         count(*) filter (where admin_entered) as likely_admin_entered
  from r
  group by 1
),
weeks as (
  select generate_series(min(week_start),
                         date_trunc('week', now() at time zone 'Asia/Singapore')::date,
                         interval '1 week')::date as week_start
  from w
)
select weeks.week_start,
       coalesce(w.requests, 0)             as requests,
       coalesce(w.sessions, 0)             as sessions,
       coalesce(w.likely_admin_entered, 0) as likely_admin_entered,
       weeks.week_start = date_trunc('week', now() at time zone 'Asia/Singapore')::date as partial_week
from weeks
left join w using (week_start)
order by 1;

-- Estimated approval wait by submission window (SGT), per period: the distribution per
-- window plus each window's n and median. Weekend = Fri 18:00 to Sun 23:59; late night =
-- weekday 23:00-07:00. All three windows appear in every period, even when empty.
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
w as (
  select p.period,
         extract(epoch from r.last_update - r.asked) / 3600 as wait_hours,
         case
           when extract(isodow from t.a) in (6, 7)
             or (extract(isodow from t.a) = 5 and extract(hour from t.a) >= 18) then 'Weekend'
           when extract(hour from t.a) >= 23 or extract(hour from t.a) < 7    then 'Weekday late night'
           else 'Weekday daytime'
         end as submitted_window
  from periods p
  join req r on r.asked at time zone 'Asia/Singapore' >= p.start_local and r.asked at time zone 'Asia/Singapore' < p.end_local
  cross join lateral (select r.asked at time zone 'Asia/Singapore' as a) t
  where r.approved and not r.admin_entered
),
wins(submitted_window) as (
  values ('Weekday daytime'), ('Weekend'), ('Weekday late night')
),
stats as (
  select p.period_order, p.period, wins.submitted_window,
         count(w.wait_hours) as window_requests,
         round((percentile_cont(0.5) within group (order by w.wait_hours))::numeric, 1) as window_median_hours
  from periods p
  cross join wins
  left join w on w.period = p.period and w.submitted_window = wins.submitted_window
  group by 1, 2, 3
),
bins(bin_order, wait_bin, lo, hi) as (
  values (1, 'Under 1h', -1e9, 1), (2, '1-6h', 1, 6), (3, '6-24h', 6, 24),
         (4, '1-2 days', 24, 48), (5, '2+ days', 48, 1e9)
)
select s.period_order, s.period, s.submitted_window, b.bin_order, b.wait_bin,
       count(w.wait_hours) as requests, s.window_requests, s.window_median_hours
from stats s
cross join bins b
left join w on w.period = s.period and w.submitted_window = s.submitted_window
           and w.wait_hours >= b.lo and w.wait_hours < b.hi
group by 1, 2, 3, 4, 5, 7, 8
order by 1, 3, 4;

-- Estimated approval wait by when the request was submitted (SGT), as a distribution
-- per window plus each window's median, so one file drives a stacked bar with labels.
-- Windows: weekend = Fri 18:00 to Sun 23:59; late night = weekday 23:00-07:00.
with pub as (
  select min(created_at) as asked, max(updated_at) as last_update
  from public.bookings
  group by coalesce(group_id, id)
  having bool_and(status = 'approved') and not bool_and(updated_at = created_at)
),
w as (
  select extract(epoch from last_update - asked) / 3600 as wait_hours,
         case
           when extract(isodow from a) in (6, 7)
             or (extract(isodow from a) = 5 and extract(hour from a) >= 18) then 'Weekend'
           when extract(hour from a) >= 23 or extract(hour from a) < 7    then 'Weekday late night'
           else 'Weekday daytime'
         end as submitted_window
  from pub, lateral (select asked at time zone 'Asia/Singapore' as a) t
),
stats as (
  select submitted_window,
         count(*) as window_requests,
         round((percentile_cont(0.5) within group (order by wait_hours))::numeric, 1) as window_median_hours
  from w group by 1
),
bins(bin_order, wait_bin, lo, hi) as (
  values (1, 'Under 1h', -1e9, 1), (2, '1-6h', 1, 6), (3, '6-24h', 6, 24),
         (4, '1-2 days', 24, 48), (5, '2+ days', 48, 1e9)
)
select s.submitted_window, b.bin_order, b.wait_bin,
       count(w.wait_hours) as requests,
       s.window_requests, s.window_median_hours
from stats s
cross join bins b
left join w on w.submitted_window = s.submitted_window
           and w.wait_hours >= b.lo and w.wait_hours < b.hi
group by 1, 2, 3, 5, 6
order by 1, 2;

-- How long sessions run, per period: approved sessions that took place in the period,
-- binned by duration, plus the period median.
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
s as (
  select p.period, extract(epoch from b.end_time - b.start_time) / 3600 as hours
  from periods p
  join public.bookings b
    on b.status = 'approved'
   and b.start_time at time zone 'Asia/Singapore' >= p.start_local
   and b.start_time at time zone 'Asia/Singapore' <  p.end_local
),
med as (
  select period, round((percentile_cont(0.5) within group (order by hours))::numeric, 1) as median_hours
  from s group by 1
),
bins(bin_order, bin, lo, hi) as (
  values (1, 'Up to 1h', 0, 1), (2, '1-2h', 1, 2), (3, '2-3h', 2, 3),
         (4, '3-4h', 3, 4), (5, 'Over 4h', 4, 1e9)
)
select p.period_order, p.period, bins.bin_order, bins.bin, count(s.hours) as sessions, med.median_hours
from periods p
cross join bins
left join s on s.period = p.period and s.hours > bins.lo and s.hours <= bins.hi
left join med on med.period = p.period
group by 1, 2, 3, 4, 6
order by 1, 3;

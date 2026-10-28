-- Hour slots in use by weekday x hour (SGT) per period, all 168 cells per period (zeros
-- included); each slot counts once even if two sessions share it. weeks = complete weeks in the period from the first booked week, so
-- booked_hours / weeks is the share of weeks that hour slot was in use. A partial hour
-- counts as a full one. Approved sessions cannot overlap (exclude constraint).
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
first_week as (
  select date_trunc('week', min(start_time at time zone 'Asia/Singapore')) as w
  from public.bookings where status = 'approved'
),
pw as (
  select p.*, greatest(p.start_local, (select w from first_week)) as eff_start from periods p
),
h as (
  -- distinct: back-to-back sessions sharing a partial hour must not count that slot twice
  select distinct pw.period, s, extract(isodow from s)::int as weekday, extract(hour from s)::int as hour
  from public.bookings b
  cross join lateral generate_series(date_trunc('hour', b.start_time at time zone 'Asia/Singapore'),
                                     (b.end_time at time zone 'Asia/Singapore') - interval '1 second',
                                     interval '1 hour') s
  join pw on s >= pw.eff_start and s < pw.end_local
  where b.status = 'approved'
)
select pw.period_order, pw.period, d.weekday,
       to_char(date '2026-10-26' + d.weekday - 1, 'Dy') as weekday_name,  -- 26 Oct 2026 is a Monday
       hr.hour,
       count(h.weekday) as booked_hours,
       (extract(epoch from pw.end_local - pw.eff_start) / 604800)::int as weeks
from pw
cross join generate_series(1, 7) d(weekday)
cross join generate_series(0, 23) hr(hour)
left join h on h.period = pw.period and h.weekday = d.weekday and h.hour = hr.hour
group by pw.period_order, pw.period, pw.eff_start, pw.end_local, d.weekday, hr.hour
order by pw.period_order, d.weekday, hr.hour;

-- Evening hour slots (19:00-24:00 SGT) in use per weekday per week, for every complete
-- week from the first approved session's week to the start of the current week. Zeros are
-- filled so every week has all 7 weekdays; each slot counts once even if two sessions share
-- it, and a partial hour counts as a full one. Drives the animated availability chart,
-- which rolls these into 4-week windows (5 evening slots per weekday per week).
with bounds as (
  select date_trunc('week', now() at time zone 'Asia/Singapore') as cutoff  -- start of the current week, SGT
),
first_week as (
  select date_trunc('week', min(start_time at time zone 'Asia/Singapore')) as w
  from public.bookings where status = 'approved'
),
weeks as (
  select generate_series((select w from first_week), (select cutoff from bounds) - interval '1 week', interval '1 week') as week_start
),
slots as (
  select distinct s
  from public.bookings b
  cross join lateral generate_series(date_trunc('hour', b.start_time at time zone 'Asia/Singapore'),
                                     (b.end_time at time zone 'Asia/Singapore') - interval '1 second',
                                     interval '1 hour') s
  where b.status = 'approved'
    and extract(hour from s) >= 19
    and s < (select cutoff from bounds)
)
select weeks.week_start::date as week_start,
       d.weekday,
       to_char(date '2026-10-26' + d.weekday - 1, 'Dy') as weekday_name,  -- 26 Oct 2026 is a Monday
       count(slots.s) as evening_slots_in_use
from weeks
cross join generate_series(1, 7) d(weekday)
left join slots on date_trunc('week', slots.s) = weeks.week_start
               and extract(isodow from slots.s) = d.weekday
group by 1, 2, 3
order by 1, 2;

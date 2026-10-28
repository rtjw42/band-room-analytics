-- Booked hours by weekday x hour (SGT), approved sessions including upcoming ones.
-- All 168 cells are present (zeros included) so the heatmap has no holes. A partial
-- hour counts as a full one.
with h as (
  select extract(isodow from s)::int as weekday, extract(hour from s)::int as hour
  from public.bookings b,
       generate_series(date_trunc('hour', b.start_time at time zone 'Asia/Singapore'),
                       (b.end_time at time zone 'Asia/Singapore') - interval '1 second',
                       interval '1 hour') s
  where b.status = 'approved'
)
select d.weekday,
       to_char(date '2026-10-26' + d.weekday - 1, 'Dy') as weekday_name,  -- 26 Oct 2026 is a Monday
       hr.hour,
       count(h.weekday) as booked_hours
from generate_series(1, 7) d(weekday)
cross join generate_series(0, 23) hr(hour)
left join h on h.weekday = d.weekday and h.hour = hr.hour
group by 1, 2, 3
order by 1, 3;

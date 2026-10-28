-- How full peak evenings are: over the last 8 complete weeks (SGT, Monday start), the
-- share of 19:00-24:00 hour slots that an approved session used, per weekday. Past
-- sessions only, so upcoming bookings never inflate it. Approved sessions cannot
-- overlap (exclude constraint), and slots are counted distinct regardless.
with bounds as (
  select date_trunc('week', now() at time zone 'Asia/Singapore')                     as wk_end,
         date_trunc('week', now() at time zone 'Asia/Singapore') - interval '8 weeks' as wk_start
),
slots as (
  select distinct s as slot
  from public.bookings b, bounds,
       generate_series(date_trunc('hour', b.start_time at time zone 'Asia/Singapore'),
                       (b.end_time at time zone 'Asia/Singapore') - interval '1 second',
                       interval '1 hour') s
  where b.status = 'approved'
    and s >= bounds.wk_start and s < bounds.wk_end
    and extract(hour from s) >= 19
)
select d.weekday,
       to_char(date '2026-10-26' + d.weekday - 1, 'Dy') as weekday_name,  -- 26 Oct 2026 is a Monday
       count(slots.slot)                                   as booked_slots,
       8 * 5                                               as available_slots,
       round(100.0 * count(slots.slot) / (8 * 5), 1)       as occupancy_pct,
       (select wk_start::date from bounds)                 as window_start,
       (select (wk_end - interval '1 day')::date from bounds) as window_end
from generate_series(1, 7) d(weekday)
left join slots on extract(isodow from slots.slot) = d.weekday
group by 1, 2
order by 1;

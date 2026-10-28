-- How long sessions run: approved sessions binned by duration, plus the overall median.
with s as (
  select extract(epoch from end_time - start_time) / 3600 as hours
  from public.bookings
  where status = 'approved'
),
bins(bin_order, bin, lo, hi) as (
  values (1, 'Up to 1h', 0, 1), (2, '1-2h', 1, 2), (3, '2-3h', 2, 3),
         (4, '3-4h', 3, 4), (5, 'Over 4h', 4, 1e9)
)
select bins.bin_order, bins.bin, count(s.hours) as sessions,
       (select round((percentile_cont(0.5) within group (order by hours))::numeric, 1) from s) as median_hours
from bins
left join s on s.hours > bins.lo and s.hours <= bins.hi
group by 1, 2
order by 1;

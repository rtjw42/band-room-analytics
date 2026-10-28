-- How far ahead bookers ask: public approved requests, submission to first session,
-- pre-binned (aggregates only). Empty bins are kept so the histogram is honest.
with pub as (
  select min(created_at) as asked, min(start_time) as first_session
  from public.bookings
  group by coalesce(group_id, id)
  having bool_and(status = 'approved') and not bool_and(updated_at = created_at)
),
d as (
  select extract(epoch from first_session - asked) / 86400 as days from pub
),
bins(bin_order, bin, lo, hi) as (
  values (1, 'Under 1 day', -1e9, 1), (2, '1-2 days', 1, 2), (3, '2-3 days', 2, 3),
         (4, '3-7 days', 3, 7), (5, '1-2 weeks', 7, 14), (6, '2+ weeks', 14, 1e9)
)
select bins.bin_order, bins.bin, count(d.days) as requests
from bins
left join d on d.days >= bins.lo and d.days < bins.hi
group by 1, 2
order by 1;

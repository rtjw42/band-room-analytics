-- Data-quality counts, long format. Each row is a check against public.bookings with
-- the number of affected requests or sessions; interpretation lives in the report.
with req as (
  select min(created_at)                   as asked,
         max(updated_at)                   as last_update,
         min(start_time)                   as first_session,
         bool_and(status = 'approved')     as approved,
         bool_and(updated_at = created_at) as admin_entered
  from public.bookings
  group by coalesce(group_id, id)
)
select sort, check_name, affected, unit
from (values
  (1, 'Requests entered by admins (inserted already approved)',
      (select count(*) from req where approved and admin_entered), 'requests'),
  (2, 'Requests approved after their first session started (estimated)',
      (select count(*) from req where approved and not admin_entered and first_session < last_update), 'requests'),
  (3, 'Sessions entered after they started (backfilled)',
      (select count(*) from public.bookings where created_at > start_time), 'sessions'),
  (4, 'Sessions longer than 6 hours',
      (select count(*) from public.bookings where status = 'approved' and end_time - start_time > interval '6 hours'), 'sessions'),
  (5, 'Sessions running past 03:00 SGT',
      (select count(*) from public.bookings
       where status = 'approved'
         and (end_time at time zone 'Asia/Singapore')::date > (start_time at time zone 'Asia/Singapore')::date
         and (end_time at time zone 'Asia/Singapore')::time > time '03:00'), 'sessions'),
  (6, 'Approved sessions later displaced by an overlapping approval',
      (select count(*) from public.bookings where status = 'rejected'), 'sessions'),
  (7, 'Pending requests at snapshot time',
      (select count(distinct coalesce(group_id, id)) from public.bookings where status = 'pending'), 'requests')
) v(sort, check_name, affected, unit)
order by sort;

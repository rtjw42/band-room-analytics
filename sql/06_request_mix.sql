-- Request mix: booking type (approved) and outcome, as dimension / label / counts.
with req as (
  select coalesce(b.group_id, b.id)     as rid,
         coalesce(g.kind, 'one-off')    as kind,
         bool_and(b.status = 'approved') as approved,
         bool_or(b.status = 'rejected')  as bumped,
         count(*)                        as sessions
  from public.bookings b
  left join public.booking_groups g on g.id = b.group_id
  group by 1, 2
)
select 'Type' as dimension, kind as label, count(*) as requests, sum(sessions) as sessions
from req where approved group by kind
union all
select 'Outcome', case when bumped then 'Bumped' else 'Approved' end, count(*), sum(sessions)
from req group by 2
order by 1, 3 desc;

-- 006_calendar_event_end_repeat.sql
-- Add end date/time and simple repeat rules to standalone calendar events.

alter table public.calendar_events
  add column if not exists end_date date;

alter table public.calendar_events
  add column if not exists end_time time;

alter table public.calendar_events
  add column if not exists repeat_rule text not null default 'none';

update public.calendar_events
set end_date = event_date
where end_date is null;

update public.calendar_events
set end_time = (event_time + interval '1 hour')::time
where all_day = false and end_time is null and event_time is not null;

alter table public.calendar_events
  alter column end_date set not null;

alter table public.calendar_events
  drop constraint if exists calendar_events_time_check;

alter table public.calendar_events
  add constraint calendar_events_time_check
  check (
    end_date >= event_date
    and (
      (all_day = true and event_time is null and end_time is null)
      or
      (
        all_day = false
        and event_time is not null
        and end_time is not null
        and (end_date > event_date or end_time > event_time)
      )
    )
  );

alter table public.calendar_events
  drop constraint if exists calendar_events_repeat_rule_check;

alter table public.calendar_events
  add constraint calendar_events_repeat_rule_check
  check (repeat_rule in ('none', 'daily', 'weekly', 'monthly', 'yearly'));

create index if not exists idx_calendar_events_user_repeat_range
  on public.calendar_events (user_id, repeat_rule, event_date, end_date);

notify pgrst, 'reload schema';

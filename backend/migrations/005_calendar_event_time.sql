-- 005_calendar_event_time.sql
-- Add optional time and all-day semantics to standalone calendar events.
--
-- Existing date-only rows remain all-day events.

alter table public.calendar_events
  add column if not exists event_time time;

alter table public.calendar_events
  add column if not exists all_day boolean not null default true;

alter table public.calendar_events
  drop constraint if exists calendar_events_time_check;

alter table public.calendar_events
  add constraint calendar_events_time_check
  check (
    (all_day = true and event_time is null)
    or
    (all_day = false and event_time is not null)
  );

create index if not exists idx_calendar_events_user_date_time
  on public.calendar_events (user_id, event_date, all_day, event_time);

notify pgrst, 'reload schema';

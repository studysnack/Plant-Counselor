import { apiGet, apiPost, apiPatch, apiDelete, downloadFile } from "./client";

export interface SummaryStats {
  active_concerns: number;
  active_schedules: number;
  harvested_this_month: number;
  wilting_count: number;
  rot_count: number;
  total_plants: number;
}

export interface CalEvent {
  id: string;
  title: string;
  status: string;
  type: string;
  detail: string;
  plant_name: string;
  plant_id: string | null;
  date?: string;
  end_date?: string;
  time?: string | null;
  end_time?: string | null;
  all_day?: boolean;
  repeat_rule?: CalendarEventRepeatRule;
  occurrence_date?: string;
  color?: CalendarEventColor;
  /** "bud" = derived from a bud deadline · "event" = standalone calendar event */
  source: "bud" | "event";
}

export const getSummary = () => apiGet<SummaryStats>("/stats/summary");

export const getBriefing = () => apiGet<{ briefing: string }>("/briefing/today");

export const getCalendar = (from: string, to: string) =>
  apiGet<{ events: Record<string, CalEvent[]> }>(
    `/calendar?from=${from}&to=${to}`
  );

// ── Standalone calendar events (not buds) ────────────────────────────────────

export interface CalendarEvent {
  id: string;
  title: string;
  detail: string;
  date: string;
  end_date: string;
  time: string | null;
  end_time: string | null;
  all_day: boolean;
  repeat_rule: CalendarEventRepeatRule;
  plant_id: string | null;
  color: CalendarEventColor;
  conflicts?: CalendarConflict[];
}

export type CalendarEventColor = "olive" | "blue" | "yellow" | "red" | "pink" | "purple";
export type CalendarEventRepeatRule = "none" | "daily" | "weekly" | "monthly" | "yearly";
export interface CalendarConflict {
  event_id: string;
  title: string;
  date: string;
  time: string;
  end_time: string;
  repeat_rule: CalendarEventRepeatRule;
}

export const createCalendarEvent = (body: {
  title: string;
  date: string;
  end_date?: string;
  time?: string | null;
  end_time?: string | null;
  all_day?: boolean;
  repeat_rule?: CalendarEventRepeatRule;
  plant_id?: string | null;
  detail?: string;
  color?: CalendarEventColor;
}) => apiPost<CalendarEvent>("/calendar/events", body);

export const updateCalendarEvent = (
  id: string,
  body: {
    title?: string;
    date?: string;
    end_date?: string;
    time?: string | null;
    end_time?: string | null;
    all_day?: boolean;
    repeat_rule?: CalendarEventRepeatRule;
    plant_id?: string | null;
    detail?: string;
    color?: CalendarEventColor;
  }
) => apiPatch<CalendarEvent>(`/calendar/events/${id}`, body);

export const deleteCalendarEvent = (id: string) =>
  apiDelete<{ deleted_id: string }>(`/calendar/events/${id}`);

export const undoLastAction = () =>
  apiPost<{ kind: string; label: string; id: string }>("/undo/last");

export const exportUserData = (format: "json" | "csv" | "ics") =>
  downloadFile(
    `/export/${format}`,
    format === "ics" ? "plant-counselor-calendar.ics" : `plant-counselor-export.${format}`
  );

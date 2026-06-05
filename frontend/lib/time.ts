const SEOUL_TIME_ZONE = "Asia/Seoul";

const dateFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: SEOUL_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const longDateFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: SEOUL_TIME_ZONE,
  year: "numeric",
  month: "long",
  day: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: SEOUL_TIME_ZONE,
  year: "numeric",
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const headerDateFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: SEOUL_TIME_ZONE,
  month: "long",
  day: "numeric",
  weekday: "long",
});

const dateTimePartsFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: SEOUL_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

function toDate(value: string | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

export function formatKstDate(value: string | Date): string {
  return dateFormatter.format(toDate(value));
}

export function formatKstLongDate(value: string | Date): string {
  return longDateFormatter.format(toDate(value));
}

export function formatKstDateTime(value: string | Date): string {
  return dateTimeFormatter.format(toDate(value));
}

export function formatKstHeaderDate(value: string | Date): string {
  return headerDateFormatter.format(toDate(value));
}

export function formatKstTimestamp(value: string | Date): string {
  const parts = dateTimePartsFormatter.formatToParts(toDate(value));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}:${get("second")}`;
}

export function formatRelativeKst(value: string): string {
  const diffSeconds = (Date.now() - new Date(value).getTime()) / 1000;
  if (diffSeconds < 60) return "방금";
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}분 전`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}시간 전`;
  return formatKstDate(value);
}

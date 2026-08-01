const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

export function formatToday(now = new Date()): string {
  const formatted = dateFormatter.format(now);
  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
}

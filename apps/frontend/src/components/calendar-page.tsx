import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Filter } from "lucide-react";

import { api, CalendarEvent, jsonBody, User } from "../lib/api";

type Mode = "month" | "week" | "day" | "list";

function dayStart(value: Date) {
  const result = new Date(value);
  result.setHours(0, 0, 0, 0);
  return result;
}

function range(mode: Mode, cursor: Date): [Date, Date] {
  if (mode === "month") {
    const start = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    return [start, new Date(start.getFullYear(), start.getMonth(), start.getDate() + 42)];
  }
  if (mode === "week") {
    const start = dayStart(cursor);
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    return [start, new Date(start.getFullYear(), start.getMonth(), start.getDate() + 7)];
  }
  if (mode === "day") {
    const start = dayStart(cursor);
    return [start, new Date(start.getFullYear(), start.getMonth(), start.getDate() + 1)];
  }
  const start = dayStart(cursor);
  return [start, new Date(start.getFullYear(), start.getMonth() + 3, start.getDate())];
}

function isoDay(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

export function CalendarPage({
  onOpen,
  onToday,
}: {
  onOpen: (event: CalendarEvent) => void;
  onToday: () => void;
}) {
  const [members, setMembers] = useState<User[]>([]);
  const [mode, setMode] = useState<Mode>("month");
  const [cursor, setCursor] = useState(() => new Date());
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [filters, setFilters] = useState({ user: "", type: "", status: "", scope: "" });
  const [error, setError] = useState("");
  const [start, end] = useMemo(() => range(mode, cursor), [mode, cursor]);
  const longPress = useRef<number | null>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
    if (filters.user) params.set("user_id", filters.user);
    if (filters.type) params.set("type", filters.type);
    if (filters.status) params.set("status", filters.status);
    if (filters.scope) params.set("scope", filters.scope);
    try {
      setEvents(await api<CalendarEvent[]>(`/calendar?${params}`));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить календарь");
    }
  }, [end, filters, start]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  useEffect(() => {
    void api<User[]>("/family/members")
      .then(setMembers)
      .catch(() => undefined);
  }, []);

  async function move(event: CalendarEvent, targetDay?: string) {
    if (!event.editable) return;
    const selected =
      targetDay ?? window.prompt("Новая дата (ГГГГ-ММ-ДД)", event.starts_at.slice(0, 10));
    if (!selected) return;
    const current = new Date(event.starts_at);
    const next = new Date(
      `${selected}T${String(current.getHours()).padStart(2, "0")}:${String(current.getMinutes()).padStart(2, "0")}:00`,
    );
    const recurrenceScope = event.recurring
      ? window.confirm("Изменить всю серию? Нажмите «Отмена» только для этого экземпляра.")
        ? "series"
        : "instance"
      : "instance";
    await api("/calendar/move", {
      method: "POST",
      ...jsonBody({
        source_type: event.source_type,
        source_id: event.source_id,
        starts_at: next.toISOString(),
        recurrence_scope: recurrenceScope,
      }),
    });
    await load();
  }

  function navigate(direction: number) {
    const next = new Date(cursor);
    if (mode === "month") next.setMonth(next.getMonth() + direction);
    else if (mode === "week") next.setDate(next.getDate() + 7 * direction);
    else next.setDate(next.getDate() + direction);
    setCursor(next);
  }

  const days = Array.from(
    { length: Math.round((end.getTime() - start.getTime()) / 86400000) },
    (_, index) => {
      const day = new Date(start);
      day.setDate(day.getDate() + index);
      return day;
    },
  );

  return (
    <main className="main-content module-page calendar-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Общий ритм семьи</span>
          <h1>Календарь</h1>
          <p>Дела, покупки, обслуживание, гарантии и хранение.</p>
        </div>
      </header>
      <section className="calendar-toolbar">
        <div className="calendar-nav">
          <button onClick={() => navigate(-1)} aria-label="Назад">
            <ChevronLeft />
          </button>
          <button onClick={() => setCursor(new Date())}>Сегодня</button>
          <button onClick={() => navigate(1)} aria-label="Вперёд">
            <ChevronRight />
          </button>
        </div>
        <strong>{cursor.toLocaleDateString("ru-RU", { month: "long", year: "numeric" })}</strong>
        <div className="mode-switch">
          {(["month", "week", "day", "list"] as Mode[]).map((item) => (
            <button
              key={item}
              className={mode === item ? "is-active" : ""}
              onClick={() => setMode(item)}
            >
              {{ month: "Месяц", week: "Неделя", day: "День", list: "Список" }[item]}
            </button>
          ))}
        </div>
      </section>
      <section className="calendar-filters">
        <Filter />
        <select
          aria-label="Участник"
          value={filters.user}
          onChange={(e) => setFilters({ ...filters, user: e.target.value })}
        >
          <option value="">Все участники</option>
          {members.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Тип"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          {["task", "shopping", "maintenance", "meter", "warranty", "storage"].map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select
          aria-label="Статус"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">Все статусы</option>
          <option value="open">Открыто</option>
          <option value="planned">Запланировано</option>
          <option value="completed">Выполнено</option>
          <option value="overdue">Просрочено</option>
        </select>
        <select
          aria-label="Область"
          value={filters.scope}
          onChange={(e) => setFilters({ ...filters, scope: e.target.value })}
        >
          <option value="">Личное и общее</option>
          <option value="personal">Личное</option>
          <option value="shared">Общее</option>
        </select>
      </section>
      {error && <p className="form-error">{error}</p>}
      {mode === "month" ? (
        <section className="calendar-grid">
          {days.map((day) => {
            const key = isoDay(day);
            const dayEvents = events.filter((item) => item.starts_at.slice(0, 10) === key);
            return (
              <article
                key={key}
                className={`calendar-day${key === isoDay(new Date()) ? " is-today" : ""}`}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  const id = e.dataTransfer.getData("text/event-id");
                  const event = events.find((item) => item.id === id);
                  if (event) void move(event, key);
                }}
              >
                <button
                  className="calendar-day-number"
                  onClick={() =>
                    key === isoDay(new Date()) ? onToday() : (setCursor(day), setMode("day"))
                  }
                >
                  {day.getDate()}
                </button>
                {dayEvents.slice(0, 4).map((event) => (
                  <button
                    key={event.id}
                    className={`calendar-event ${event.source_type}`}
                    draggable={event.editable}
                    onDragStart={(e) => e.dataTransfer.setData("text/event-id", event.id)}
                    onPointerDown={() => {
                      longPress.current = window.setTimeout(() => void move(event), 650);
                    }}
                    onPointerUp={() => {
                      if (longPress.current) window.clearTimeout(longPress.current);
                    }}
                    onClick={() => onOpen(event)}
                  >
                    <span>
                      {new Date(event.starts_at).toLocaleTimeString("ru-RU", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                    {event.title}
                  </button>
                ))}
              </article>
            );
          })}
        </section>
      ) : (
        <section className="calendar-agenda">
          {events.length === 0 && (
            <p className="empty-state">
              <CalendarDays />
              На выбранный период событий нет.
            </p>
          )}
          {events.map((event) => (
            <button
              className="agenda-event module-card"
              key={event.id}
              onClick={() => onOpen(event)}
              onContextMenu={(e) => {
                e.preventDefault();
                void move(event);
              }}
            >
              <time>
                {new Date(event.starts_at).toLocaleString("ru-RU", {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
              </time>
              <strong>{event.title}</strong>
              <span>
                {event.source_type} · {event.status}
              </span>
            </button>
          ))}
        </section>
      )}
    </main>
  );
}

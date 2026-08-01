import { CalendarDays, Check, Plus, WifiOff } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, jsonBody, ShoppingList, TaskItem, User } from "../lib/api";
import { formatToday } from "../lib/date";
import { ru } from "../lib/i18n";
import {
  cacheToday,
  cachedToday,
  completeTaskOperation,
  newOperationId,
  pendingTaskCount,
  queueTaskCompletion,
  syncTaskQueue,
} from "../lib/task-offline";

function dueLabel(task: TaskItem): string {
  if (!task.due_at) return ru.tasks.noTime;
  return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(
    new Date(task.due_at),
  );
}

export function TodayDashboard({
  user,
  onOpenShopping,
}: {
  user: User;
  onOpenShopping: () => void;
}) {
  const storedScope = localStorage.getItem("domovoy.today.scope") === "all" ? "all" : "mine";
  const [scope, setScope] = useState<"mine" | "all">(storedScope);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [draft, setDraft] = useState("");
  const [shopping, setShopping] = useState<ShoppingList[]>([]);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(!navigator.onLine);
  const [pending, setPending] = useState(pendingTaskCount());

  const load = useCallback(async () => {
    try {
      const [taskData, shoppingData] = await Promise.all([
        api<TaskItem[]>(`/tasks/today?scope=${scope}`),
        api<ShoppingList[]>("/shopping/today"),
      ]);
      setTasks(taskData);
      cacheToday(user.id, scope, taskData);
      setShopping(shoppingData);
      setError("");
    } catch (caught) {
      const saved = cachedToday(user.id, scope);
      if (saved) {
        setTasks(saved);
        setOffline(true);
        setError("");
      } else {
        setError(caught instanceof Error ? caught.message : ru.common.error);
      }
    }
  }, [scope, user.id]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  useEffect(() => {
    const wentOffline = () => setOffline(true);
    const wentOnline = () => {
      setOffline(false);
      void syncTaskQueue().then((count) => {
        setPending(count);
        void load();
      });
    };
    window.addEventListener("offline", wentOffline);
    window.addEventListener("online", wentOnline);
    return () => {
      window.removeEventListener("offline", wentOffline);
      window.removeEventListener("online", wentOnline);
    };
  }, [load]);

  const open = useMemo(
    () =>
      tasks
        .filter((task) => task.status !== "completed")
        .sort((left, right) => {
          if (!left.due_at) return 1;
          if (!right.due_at) return -1;
          return new Date(left.due_at).getTime() - new Date(right.due_at).getTime();
        }),
    [tasks],
  );
  const completed = tasks.filter((task) => task.status === "completed");

  function chooseScope(next: "mine" | "all") {
    localStorage.setItem("domovoy.today.scope", next);
    setScope(next);
  }

  async function complete(task: TaskItem) {
    const operationId = newOperationId();
    const before = tasks;
    const optimistic: TaskItem = {
      ...task,
      status: task.requires_adult_review && user.role === "child" ? "awaiting_review" : "completed",
      completed_by_id: user.id,
      completed_at: new Date().toISOString(),
    };
    setTasks((items) => items.map((item) => (item.id === task.id ? optimistic : item)));
    const operation = {
      kind: "complete-task" as const,
      operationId,
      taskId: task.id,
      completedSubtaskIds: task.subtasks.map((item) => item.id),
    };
    if (!navigator.onLine) {
      queueTaskCompletion(operation);
      setPending(pendingTaskCount());
      setOffline(true);
      return;
    }
    try {
      const updated = await completeTaskOperation(task, operationId);
      setTasks((items) => items.map((item) => (item.id === task.id ? updated : item)));
    } catch (caught) {
      if (!(caught instanceof Error) || caught.name === "TypeError") {
        queueTaskCompletion(operation);
        setPending(pendingTaskCount());
        setOffline(true);
      } else {
        setTasks(before);
        setError(caught.message);
      }
    }
  }

  async function addTask(event: FormEvent) {
    event.preventDefault();
    const title = draft.trim();
    if (!title) return;
    try {
      const created = await api<TaskItem>("/tasks", {
        method: "POST",
        ...jsonBody({
          title,
          due_at: new Date().toISOString(),
          assignment_mode: "fixed",
          assignee_ids: [user.id],
          repeat: { kind: "none" },
        }),
      });
      setTasks((items) => [...items, created]);
      setDraft("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }

  const progress = tasks.length ? Math.round((completed.length / tasks.length) * 100) : 0;
  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="mobile-brand">{ru.brand}</p>
          <h1>
            {ru.today.greeting}, {user.name}
          </h1>
          <p className="date-line">
            <CalendarDays aria-hidden="true" /> <span>{formatToday()}</span>
          </p>
        </div>
      </header>
      {(offline || pending > 0) && (
        <p className="offline-banner" role="status">
          <WifiOff aria-hidden="true" />
          {offline ? "Офлайн: показана сохранённая версия." : "Синхронизация"} Операций в очереди:{" "}
          {pending}.
        </p>
      )}
      <div className="scope-switch" role="group" aria-label={ru.today.scope}>
        <button className={scope === "mine" ? "is-active" : ""} onClick={() => chooseScope("mine")}>
          {ru.today.mine}
        </button>
        <button className={scope === "all" ? "is-active" : ""} onClick={() => chooseScope("all")}>
          {ru.today.all}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
      <section className="dashboard-grid">
        <section className="card today-card">
          <div className="card-heading">
            <h2>{ru.today.title}</h2>
            <span className="filter-chip">{open.length}</span>
          </div>
          <div className="task-list">
            {open.map((task) => (
              <article className="task-row live-task-row" key={task.id}>
                <button
                  className="task-checkbox"
                  type="button"
                  onClick={() => void complete(task)}
                  aria-label={`${ru.tasks.complete}: ${task.title}`}
                />
                <div className="task-copy">
                  <strong>{task.title}</strong>
                  <span>
                    {dueLabel(task)} · {task.category}
                  </span>
                </div>
              </article>
            ))}
            {open.length === 0 && <p className="empty-state">{ru.today.empty}</p>}
          </div>
          {user.role !== "child" && (
            <form className="quick-add" onSubmit={(event) => void addTask(event)}>
              <label className="sr-only" htmlFor="quick-task">
                {ru.today.quickTaskPlaceholder}
              </label>
              <input
                id="quick-task"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={ru.today.quickTaskPlaceholder}
              />
              <button type="submit" aria-label={ru.today.quickAdd}>
                <Plus aria-hidden="true" />
              </button>
            </form>
          )}
          <details className="completed-block">
            <summary>
              {ru.today.completedTasks} · {completed.length}
            </summary>
            {completed.map((task) => (
              <p key={task.id}>
                <Check aria-hidden="true" /> {task.title}
              </p>
            ))}
          </details>
        </section>
        <aside className="summary-column">
          <section className="card progress-card">
            <div className="progress-copy">
              <h2>{ru.today.dailyProgress}</h2>
              <strong>
                {completed.length} из {tasks.length}
              </strong>
              <span>
                {progress}% {ru.today.completed}
              </span>
              <div className="progress-track" aria-hidden="true">
                <span style={{ width: `${progress}%` }} />
              </div>
            </div>
          </section>
          {shopping.map((list) => (
            <section className="card shopping-card" key={list.id}>
              <h2>{list.title}</h2>
              <p>
                {list.scheduled_at
                  ? new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(
                      new Date(list.scheduled_at),
                    )
                  : ""}
              </p>
              <p className="shopping-count">{list.items.length} позиций</p>
              <ul>
                {list.items.slice(0, 4).map((item) => (
                  <li key={item.id}>{item.name}</li>
                ))}
              </ul>
              <button type="button" onClick={onOpenShopping}>
                {ru.today.openList}
              </button>
            </section>
          ))}
        </aside>
      </section>
    </main>
  );
}

import { Check, Plus, RotateCw } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError, jsonBody, TaskItem, User } from "../lib/api";
import { ru } from "../lib/i18n";

type View = "active" | "completed" | "recurring";

function whenLabel(value: string | null): string {
  if (!value) return ru.tasks.noDate;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function groupName(task: TaskItem): string {
  if (!task.due_at) return ru.tasks.groups.noDate;
  const due = new Date(task.due_at);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dueDay = new Date(due.getFullYear(), due.getMonth(), due.getDate());
  if (dueDay < today && task.status !== "completed") return ru.tasks.groups.overdue;
  if (dueDay.getTime() === today.getTime()) return ru.tasks.groups.today;
  if (dueDay.getTime() <= today.getTime() + 7 * 86400000) return ru.tasks.groups.week;
  return ru.tasks.groups.later;
}

export function TasksPage({ currentUser }: { currentUser: User }) {
  const [view, setView] = useState<View>("active");
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [members, setMembers] = useState<User[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [taskData, memberData] = await Promise.all([
        api<TaskItem[]>(`/tasks?view=${view}`),
        api<User[]>("/family/members"),
      ]);
      setTasks(taskData);
      setMembers(memberData.filter((member) => member.is_active));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }, [view]);

  useEffect(() => {
    void load();
  }, [load]);

  const grouped = useMemo(() => {
    const groups = new Map<string, TaskItem[]>();
    for (const task of tasks) {
      const group = groupName(task);
      groups.set(group, [...(groups.get(group) ?? []), task]);
    }
    return [...groups.entries()];
  }, [tasks]);

  async function complete(task: TaskItem) {
    setBusy(true);
    setError("");
    try {
      const updated = await api<TaskItem>(`/tasks/${task.id}/complete`, {
        method: "POST",
        ...jsonBody({ completed_subtask_ids: task.subtasks.map((item) => item.id) }),
      });
      setTasks((items) => items.map((item) => (item.id === task.id ? updated : item)));
      if (updated.status === "completed" && view === "active") await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : ru.common.error);
    } finally {
      setBusy(false);
    }
  }

  async function review(task: TaskItem, decision: "approve" | "reject") {
    const comment = decision === "reject" ? window.prompt(ru.tasks.rejectComment) : undefined;
    if (decision === "reject" && !comment) return;
    const updated = await api<TaskItem>(`/tasks/${task.id}/review`, {
      method: "POST",
      ...jsonBody({ decision, comment }),
    });
    setTasks((items) => items.map((item) => (item.id === task.id ? updated : item)));
  }

  return (
    <main className="main-content module-page">
      <header className="page-header">
        <div>
          <p className="mobile-brand">{ru.brand}</p>
          <h1>{ru.tasks.title}</h1>
          <p className="page-subtitle">{ru.tasks.description}</p>
        </div>
        {currentUser.role !== "child" && (
          <button className="primary-button" type="button" onClick={() => setShowCreate(true)}>
            <Plus aria-hidden="true" /> {ru.tasks.add}
          </button>
        )}
      </header>
      <div className="tabs" role="tablist" aria-label={ru.tasks.title}>
        {(["active", "completed", "recurring"] as const).map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={view === item}
            className={view === item ? "is-active" : ""}
            onClick={() => setView(item)}
          >
            {ru.tasks.views[item]}
          </button>
        ))}
      </div>
      {error && <p className="form-error">{error}</p>}
      <section className="task-groups">
        {grouped.map(([group, items]) => (
          <section key={group} className="task-group">
            <h2>{group}</h2>
            <div className="card module-list">
              {items.map((task) => (
                <article className={`module-row priority-${task.priority}`} key={task.id}>
                  <button
                    className="task-checkbox"
                    type="button"
                    disabled={busy || !["open", "rejected"].includes(task.status)}
                    onClick={() => void complete(task)}
                    aria-label={`${ru.tasks.complete}: ${task.title}`}
                  >
                    {task.status === "completed" && <Check aria-hidden="true" />}
                  </button>
                  <div className="module-row-copy">
                    <strong>{task.title}</strong>
                    <span>
                      {task.category} · {whenLabel(task.due_at)}
                      {task.room ? ` · ${task.room}` : ""}
                    </span>
                    {task.status === "awaiting_review" && <em>{ru.tasks.awaitingReview}</em>}
                    {task.status === "rejected" && <em>{task.review_comment}</em>}
                  </div>
                  {task.repeat.kind !== "none" && (
                    <span className="status-chip">
                      <RotateCw aria-hidden="true" /> {ru.tasks.repeat}
                    </span>
                  )}
                  {task.status === "awaiting_review" && currentUser.role !== "child" && (
                    <div className="row-actions">
                      <button type="button" onClick={() => void review(task, "approve")}>
                        {ru.tasks.approve}
                      </button>
                      <button type="button" onClick={() => void review(task, "reject")}>
                        {ru.tasks.reject}
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>
        ))}
        {!error && tasks.length === 0 && <p className="empty-state">{ru.tasks.empty}</p>}
      </section>
      {showCreate && (
        <TaskCreateDialog
          members={members}
          onClose={() => setShowCreate(false)}
          onCreated={(task) => {
            setTasks((items) => [task, ...items]);
            setShowCreate(false);
          }}
        />
      )}
    </main>
  );
}

function TaskCreateDialog({
  members,
  onClose,
  onCreated,
}: {
  members: User[];
  onClose: () => void;
  onCreated: (task: TaskItem) => void;
}) {
  const [mode, setMode] = useState<"fixed" | "anyone" | "multiple" | "queue">("fixed");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const selected = data.getAll("assignees").map(String);
    const due = String(data.get("due_at") ?? "");
    try {
      const created = await api<TaskItem>("/tasks", {
        method: "POST",
        ...jsonBody({
          title: data.get("title"),
          description: data.get("description") || null,
          room: data.get("room") || null,
          category: data.get("category") || "другое",
          due_at: due ? new Date(due).toISOString() : null,
          priority: data.get("priority"),
          assignment_mode: mode,
          assignee_ids: mode === "fixed" || mode === "multiple" ? selected : [],
          queue_user_ids: mode === "queue" ? selected : [],
          subtasks: String(data.get("subtasks") ?? "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          repeat: { kind: data.get("repeat") },
          requires_photo: data.get("photo") === "on",
          requires_adult_review: data.get("review") === "on",
        }),
      });
      onCreated(created);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-card wide-modal" role="dialog" aria-modal="true">
        <h2>{ru.tasks.add}</h2>
        <form className="form-grid" onSubmit={(event) => void submit(event)}>
          <label>
            {ru.tasks.fields.title}
            <input name="title" required maxLength={180} autoFocus />
          </label>
          <label>
            {ru.tasks.fields.description}
            <textarea name="description" rows={3} />
          </label>
          <div className="form-columns">
            <label>
              {ru.tasks.fields.when}
              <input name="due_at" type="datetime-local" />
            </label>
            <label>
              {ru.tasks.fields.room}
              <input name="room" />
            </label>
            <label>
              {ru.tasks.fields.category}
              <select name="category" defaultValue="уборка">
                {ru.tasks.categories.map((category) => (
                  <option key={category}>{category}</option>
                ))}
              </select>
            </label>
            <label>
              {ru.tasks.fields.priority}
              <select name="priority" defaultValue="normal">
                <option value="low">{ru.tasks.priorities.low}</option>
                <option value="normal">{ru.tasks.priorities.normal}</option>
                <option value="high">{ru.tasks.priorities.high}</option>
                <option value="urgent">{ru.tasks.priorities.urgent}</option>
              </select>
            </label>
            <label>
              {ru.tasks.fields.assignment}
              <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
                <option value="fixed">{ru.tasks.assignment.fixed}</option>
                <option value="anyone">{ru.tasks.assignment.anyone}</option>
                <option value="multiple">{ru.tasks.assignment.multiple}</option>
                <option value="queue">{ru.tasks.assignment.queue}</option>
              </select>
            </label>
            <label>
              {ru.tasks.fields.repeat}
              <select name="repeat" defaultValue="none">
                <option value="none">{ru.tasks.repeats.none}</option>
                <option value="daily">{ru.tasks.repeats.daily}</option>
                <option value="weekly">{ru.tasks.repeats.weekly}</option>
                <option value="monthly">{ru.tasks.repeats.monthly}</option>
                <option value="yearly">{ru.tasks.repeats.yearly}</option>
              </select>
            </label>
          </div>
          {mode !== "anyone" && (
            <label>
              {mode === "queue" ? ru.tasks.fields.queue : ru.tasks.fields.assignees}
              <select name="assignees" multiple={mode !== "fixed"} required size={4}>
                {members.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            {ru.tasks.fields.subtasks}
            <input name="subtasks" placeholder={ru.tasks.fields.subtasksHint} />
          </label>
          <div className="check-grid">
            <label className="check-line">
              <input type="checkbox" name="review" /> {ru.tasks.fields.review}
            </label>
            <label className="check-line">
              <input type="checkbox" name="photo" /> {ru.tasks.fields.photo}
            </label>
          </div>
          {error && <p className="form-error">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              {ru.common.cancel}
            </button>
            <button type="submit" className="primary-button" disabled={busy}>
              {ru.common.save}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

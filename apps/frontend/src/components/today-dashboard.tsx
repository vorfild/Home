import { CalendarDays, Check, ChevronRight, EllipsisVertical, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import { formatToday } from "../lib/date";
import { ru } from "../lib/i18n";

type PersonColor = "mint" | "blue" | "pale-blue";

type Task = {
  id: number;
  title: string;
  person: string;
  initial: string;
  when: string;
  color: PersonColor;
  completed: boolean;
};

const initialTasks: Task[] = [
  {
    id: 1,
    title: ru.today.tasks.waterFlowers,
    person: ru.today.people.anna,
    initial: "А",
    when: "18:00",
    color: "mint",
    completed: false,
  },
  {
    id: 2,
    title: ru.today.tasks.takeTrash,
    person: ru.today.people.alexey,
    initial: "А",
    when: "до 20:00",
    color: "blue",
    completed: false,
  },
  {
    id: 3,
    title: ru.today.tasks.vacuumLivingRoom,
    person: ru.today.people.misha,
    initial: "М",
    when: ru.nav.today,
    color: "pale-blue",
    completed: true,
  },
  {
    id: 4,
    title: ru.today.tasks.changeTowels,
    person: ru.today.people.olga,
    initial: "О",
    when: ru.nav.today,
    color: "mint",
    completed: false,
  },
];

function TaskRow({ task, onToggle }: { task: Task; onToggle: (id: number) => void }) {
  return (
    <article className={`task-row${task.completed ? " is-complete" : ""}`}>
      <button
        className="task-checkbox"
        type="button"
        aria-label={
          task.completed ? `Вернуть задачу «${task.title}»` : `Завершить задачу «${task.title}»`
        }
        aria-pressed={task.completed}
        onClick={() => onToggle(task.id)}
      >
        {task.completed && <Check aria-hidden="true" />}
      </button>
      <span className={`avatar avatar-${task.color}`}>{task.initial}</span>
      <div className="task-copy">
        <strong>{task.title}</strong>
        <span>
          {task.person} <i aria-hidden="true">·</i> {task.when}
        </span>
      </div>
      <button className="icon-button" type="button" aria-label={`Действия: ${task.title}`}>
        <EllipsisVertical aria-hidden="true" />
      </button>
    </article>
  );
}

export function TodayDashboard({ userName }: { userName: string }) {
  const [tasks, setTasks] = useState(initialTasks);
  const [draft, setDraft] = useState("");
  const completeCount = useMemo(() => tasks.filter((task) => task.completed).length, [tasks]);

  function toggleTask(id: number) {
    setTasks((current) =>
      current.map((task) => (task.id === id ? { ...task, completed: !task.completed } : task)),
    );
  }

  function addDraftTask() {
    const title = draft.trim();
    if (!title) return;
    setTasks((current) => [
      ...current,
      {
        id: Math.max(0, ...current.map((task) => task.id)) + 1,
        title,
        person: userName,
        initial: "А",
        when: ru.nav.today,
        color: "blue",
        completed: false,
      },
    ]);
    setDraft("");
  }

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="mobile-brand">{ru.brand}</p>
          <h1>
            {ru.today.greeting}, {userName}
          </h1>
          <p className="date-line">
            <CalendarDays aria-hidden="true" />
            <span>{formatToday()}</span>
          </p>
        </div>
        <button className="primary-button" type="button">
          <Plus aria-hidden="true" />
          <span>{ru.today.addTask}</span>
        </button>
      </header>

      <section className="dashboard-grid" aria-label="Сводка на сегодня">
        <section className="card today-card">
          <div className="card-heading">
            <h2>{ru.today.title}</h2>
            <span className="filter-chip">
              {ru.today.all} <b>{tasks.length}</b>
            </span>
          </div>
          <div className="task-list">
            {tasks.map((task) => (
              <TaskRow key={task.id} task={task} onToggle={toggleTask} />
            ))}
          </div>
          <form
            className="quick-add"
            onSubmit={(event) => {
              event.preventDefault();
              addDraftTask();
            }}
          >
            <label className="sr-only" htmlFor="quick-task">
              {ru.today.quickTaskPlaceholder}
            </label>
            <input
              id="quick-task"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={ru.today.quickTaskPlaceholder}
            />
            <button type="submit" aria-label="Добавить быстрое дело">
              <Plus aria-hidden="true" />
            </button>
          </form>
        </section>

        <aside className="summary-column">
          <section className="card progress-card">
            <div className="progress-copy">
              <h2>{ru.today.dailyProgress}</h2>
              <strong>
                {completeCount} из {tasks.length}
              </strong>
              <span>
                {Math.round((completeCount / tasks.length) * 100)}% {ru.today.completed}
              </span>
              <div className="progress-track" aria-hidden="true">
                <span style={{ width: `${(completeCount / tasks.length) * 100}%` }} />
              </div>
            </div>
            <div className="family-avatars" aria-label="Члены семьи">
              <span className="avatar avatar-mint">А</span>
              <span className="avatar avatar-blue">А</span>
              <span className="avatar avatar-pale-blue">М</span>
              <span className="avatar avatar-mint">О</span>
            </div>
          </section>

          <section className="card shopping-card">
            <h2>{ru.today.shoppingToday}</h2>
            <p>{ru.today.plannedFor}</p>
            <p className="shopping-count">{ru.today.positions}</p>
            <ul>
              <li>Молоко</li>
              <li>Яблоки</li>
              <li>Средство для посуды</li>
            </ul>
            <button type="button">
              <span>{ru.today.openList}</span>
              <ChevronRight aria-hidden="true" />
            </button>
          </section>
        </aside>
      </section>
    </main>
  );
}

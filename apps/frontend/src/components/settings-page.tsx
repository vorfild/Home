import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Bell,
  CheckCheck,
  Database,
  GitMerge,
  MonitorCog,
  Palette,
  Server,
  UserRound,
} from "lucide-react";

import {
  api,
  AppNotification,
  jsonBody,
  ModuleSettings,
  ServerSettings,
  SyncConflict,
  User,
  UserPreference,
} from "../lib/api";

type Tab = "profile" | "notifications" | "conflicts" | "appearance" | "modules" | "server" | "data";

const eventLabels: Record<string, string> = {
  task_assigned: "Назначено новое дело",
  task_due: "Приближается срок дела",
  task_overdue: "Дело просрочено",
  queue_turn: "Наступила очередь",
  shopping_today: "Покупки сегодня",
  shopping_changed: "Общий список существенно изменён",
  storage_review: "Истёк таймер хранения",
  maintenance_due: "Срок обслуживания",
  meter_due: "Пора передать показания",
  warranty_expiring: "Истекает гарантия",
};

function urlBase64(value: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const raw = atob((value + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (character) => character.charCodeAt(0));
}

function applyAppearance(value: UserPreference) {
  const root = document.documentElement;
  root.dataset.theme = value.theme;
  root.dataset.fontScale = value.font_scale;
  root.dataset.density = value.density;
}

export function SettingsPage({ currentUser }: { currentUser: User }) {
  const [tab, setTab] = useState<Tab>("profile");
  const [preference, setPreference] = useState<UserPreference | null>(null);
  const [modules, setModules] = useState<ModuleSettings | null>(null);
  const [server, setServer] = useState<ServerSettings | null>(null);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [conflicts, setConflicts] = useState<SyncConflict[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [prefs, moduleData, noticeData] = await Promise.all([
        api<UserPreference>("/settings/preferences"),
        api<ModuleSettings>("/settings/modules"),
        api<AppNotification[]>("/settings/notifications"),
      ]);
      setPreference(prefs);
      setModules(moduleData);
      setNotifications(noticeData);
      applyAppearance(prefs);
      if (currentUser.role !== "child") {
        setConflicts(await api<SyncConflict[]>("/sync/conflicts"));
      }
      if (currentUser.role === "admin") setServer(await api<ServerSettings>("/settings/server"));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить настройки");
    }
  }, [currentUser.role]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  async function savePreferences(next = preference) {
    if (!next) return;
    const saved = await api<UserPreference>("/settings/preferences", {
      method: "PUT",
      ...jsonBody(next),
    });
    setPreference(saved);
    applyAppearance(saved);
    setMessage("Настройки сохранены");
  }

  async function enablePush() {
    const key = await api<{ enabled: boolean; public_key: string | null }>("/settings/push/key");
    if (!key.enabled || !key.public_key) throw new Error("Web Push пока не настроен на сервере");
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64(key.public_key),
    });
    const values = subscription.toJSON();
    await api("/settings/push/subscriptions", {
      method: "POST",
      ...jsonBody({
        endpoint: values.endpoint,
        p256dh: values.keys?.p256dh,
        auth: values.keys?.auth,
      }),
    });
    if (preference) {
      const next = { ...preference, channels: { ...preference.channels, push: true } };
      setPreference(next);
      await savePreferences(next);
    }
  }

  async function saveModules(next: ModuleSettings) {
    const saved = await api<ModuleSettings>("/settings/modules", {
      method: "PUT",
      ...jsonBody(next),
    });
    setModules(saved);
    setMessage("Модули обновлены; данные сохранены");
  }

  async function saveServer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!server) return;
    const saved = await api<ServerSettings>("/settings/server", {
      method: "PUT",
      ...jsonBody({ timezone: server.timezone, domain: server.domain }),
    });
    setServer(saved);
    setMessage("Серверные настройки сохранены");
  }

  async function resolveConflict(
    conflict: SyncConflict,
    resolution: "server" | "alternative" | "manual",
  ) {
    let manualValue: unknown = null;
    if (resolution === "manual") {
      const value = window.prompt("Введите итоговое значение", String(conflict.server_value ?? ""));
      if (value === null) return;
      manualValue = value;
    }
    await api(`/sync/conflicts/${conflict.id}/resolve`, {
      method: "POST",
      ...jsonBody({ resolution, manual_value: manualValue }),
    });
    setMessage("Конфликт разрешён; выбранное значение сохранено");
    await load();
  }

  async function rejectAllConflicts() {
    await api("/sync/conflicts/reject-all", { method: "POST" });
    setMessage("Все альтернативные изменения отклонены");
    await load();
  }

  const tabs: { id: Tab; label: string; icon: typeof UserRound }[] = [
    { id: "profile", label: "Профиль", icon: UserRound },
    { id: "notifications", label: "Уведомления", icon: Bell },
    { id: "conflicts", label: "Конфликты", icon: GitMerge },
    { id: "appearance", label: "Оформление", icon: Palette },
    { id: "modules", label: "Модули", icon: MonitorCog },
    { id: "server", label: "Сервер", icon: Server },
    { id: "data", label: "Данные", icon: Database },
  ];

  return (
    <main className="main-content module-page settings-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Ваш Домовой</span>
          <h1>Настройки</h1>
          <p>Личные предпочтения и конфигурация семейного сервера.</p>
        </div>
      </header>
      {error && <p className="form-error">{error}</p>}
      {message && <p className="inline-message">{message}</p>}
      <div className="settings-layout">
        <nav className="settings-nav">
          {tabs
            .filter(
              (item) =>
                (currentUser.role === "admin" ||
                  !["modules", "server", "data"].includes(item.id)) &&
                (currentUser.role !== "child" || item.id !== "conflicts"),
            )
            .map(({ id, label, icon: Icon }) => (
              <button key={id} className={tab === id ? "is-active" : ""} onClick={() => setTab(id)}>
                <Icon />
                {label}
                {id === "notifications" && notifications.some((item) => !item.read_at) && <i />}
                {id === "conflicts" && conflicts.length > 0 && (
                  <span className="count-badge">{conflicts.length}</span>
                )}
              </button>
            ))}
        </nav>
        <section className="settings-panel">
          {tab === "profile" && (
            <>
              <h2>{currentUser.name}</h2>
              <dl className="server-facts">
                <div>
                  <dt>Логин</dt>
                  <dd>@{currentUser.login}</dd>
                </div>
                <div>
                  <dt>Роль</dt>
                  <dd>{currentUser.role}</dd>
                </div>
                <div>
                  <dt>Статус</dt>
                  <dd>{currentUser.active_absence ? "Временно отсутствует" : "Активен"}</dd>
                </div>
              </dl>
            </>
          )}
          {tab === "notifications" && preference && (
            <NotificationSettings
              value={preference}
              child={currentUser.role === "child"}
              notifications={notifications}
              onChange={setPreference}
              onSave={() => void savePreferences()}
              onPush={() =>
                void enablePush().catch((caught) =>
                  setError(caught instanceof Error ? caught.message : "Ошибка Web Push"),
                )
              }
              onReadAll={async () => {
                await api("/settings/notifications/read-all", { method: "POST" });
                await load();
              }}
            />
          )}
          {tab === "appearance" && preference && (
            <Appearance
              value={preference}
              onChange={(next) => {
                setPreference(next);
                applyAppearance(next);
              }}
              onSave={() => void savePreferences()}
            />
          )}
          {tab === "conflicts" && currentUser.role !== "child" && (
            <ConflictCenter
              conflicts={conflicts}
              admin={currentUser.role === "admin"}
              onResolve={(conflict, resolution) =>
                void resolveConflict(conflict, resolution).catch((caught) =>
                  setError(caught instanceof Error ? caught.message : "Ошибка разрешения"),
                )
              }
              onRejectAll={() =>
                void rejectAllConflicts().catch((caught) =>
                  setError(caught instanceof Error ? caught.message : "Ошибка разрешения"),
                )
              }
            />
          )}
          {tab === "modules" && modules && currentUser.role === "admin" && (
            <>
              <h2>Модули</h2>
              <p>Выключение скрывает функции и уведомления, но не удаляет данные.</p>
              <div className="settings-checks">
                {Object.entries(modules).map(([key, enabled]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={(event) =>
                        void saveModules({ ...modules, [key]: event.target.checked })
                      }
                    />
                    <span>
                      {
                        (
                          {
                            meters: "Счётчики",
                            email: "Email-уведомления",
                            shopping_prices: "Цены покупок",
                            maintenance_finances: "Финансы обслуживания",
                            task_photos: "Фото-подтверждение",
                          } as Record<string, string>
                        )[key]
                      }
                    </span>
                  </label>
                ))}
              </div>
            </>
          )}
          {tab === "server" && server && currentUser.role === "admin" && (
            <form className="form-grid" onSubmit={(event) => void saveServer(event)}>
              <h2>Сервер</h2>
              <label>
                Часовой пояс
                <input
                  value={server.timezone}
                  onChange={(e) => setServer({ ...server, timezone: e.target.value })}
                />
              </label>
              <label>
                Домен
                <input
                  value={server.domain ?? ""}
                  onChange={(e) => setServer({ ...server, domain: e.target.value || null })}
                  placeholder="https://home.example.org"
                />
              </label>
              <dl className="server-facts">
                <div>
                  <dt>Версия</dt>
                  <dd>{server.app_version}</dd>
                </div>
                <div>
                  <dt>HTTPS</dt>
                  <dd>{server.https_enabled ? "Активен" : "Не активен"}</dd>
                </div>
                <div>
                  <dt>Файлы</dt>
                  <dd>{server.files_dir}</dd>
                </div>
                <div>
                  <dt>Web Push / SMTP</dt>
                  <dd>
                    {server.web_push_configured ? "Push готов" : "Push не настроен"} ·{" "}
                    {server.smtp_configured ? "SMTP готов" : "SMTP не настроен"}
                  </dd>
                </div>
              </dl>
              <button className="primary-button">Сохранить</button>
            </form>
          )}
          {tab === "data" && currentUser.role === "admin" && (
            <>
              <h2>Данные</h2>
              <p>
                Состояние резервных копий, переносимый экспорт и импорт появятся в следующем этапе
                файлов и резервирования.
              </p>
              <div className="module-card data-placeholder">
                <Database />
                <span>Постоянные volumes подключены; операции переноса пока недоступны.</span>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}

function printable(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

function ConflictCenter({
  conflicts,
  admin,
  onResolve,
  onRejectAll,
}: {
  conflicts: SyncConflict[];
  admin: boolean;
  onResolve: (conflict: SyncConflict, resolution: "server" | "alternative" | "manual") => void;
  onRejectAll: () => void;
}) {
  return (
    <>
      <div className="section-title-row">
        <div>
          <h2>Конфликты синхронизации</h2>
          <p>Серверное значение сохраняется, пока взрослый не выберет итоговый вариант.</p>
        </div>
        {admin && conflicts.length > 0 && (
          <button className="secondary-button danger-button" onClick={onRejectAll}>
            Отклонить все альтернативы
          </button>
        )}
      </div>
      <div className="conflict-list">
        {conflicts.map((conflict) => (
          <article className="conflict-card" key={conflict.id}>
            <div>
              <strong>
                {conflict.entity_type} · {conflict.field_name}
              </strong>
              <small>{new Date(conflict.created_at).toLocaleString("ru-RU")}</small>
            </div>
            <dl>
              <div>
                <dt>На сервере</dt>
                <dd>{printable(conflict.server_value)}</dd>
              </div>
              <div>
                <dt>Альтернатива</dt>
                <dd>{printable(conflict.alternative_value)}</dd>
              </div>
            </dl>
            <div className="row-actions">
              <button onClick={() => onResolve(conflict, "server")}>Оставить серверное</button>
              <button onClick={() => onResolve(conflict, "alternative")}>
                Принять альтернативу
              </button>
              <button onClick={() => onResolve(conflict, "manual")}>Ввести вручную</button>
            </div>
          </article>
        ))}
        {conflicts.length === 0 && <p className="empty-state">Неразрешённых конфликтов нет.</p>}
      </div>
    </>
  );
}

function NotificationSettings({
  value,
  child,
  notifications,
  onChange,
  onSave,
  onPush,
  onReadAll,
}: {
  value: UserPreference;
  child: boolean;
  notifications: AppNotification[];
  onChange: (value: UserPreference) => void;
  onSave: () => void;
  onPush: () => void;
  onReadAll: () => void;
}) {
  return (
    <>
      <div className="section-title-row">
        <div>
          <h2>Центр уведомлений</h2>
          <p>{notifications.filter((item) => !item.read_at).length} непрочитанных</p>
        </div>
        <button className="secondary-button" onClick={onReadAll}>
          <CheckCheck />
          Прочитать все
        </button>
      </div>
      <div className="notification-list">
        {notifications.slice(0, 8).map((item) => (
          <article key={item.id} className={`notification-row${item.read_at ? "" : " unread"}`}>
            <Bell />
            <div>
              <strong>{item.title}</strong>
              <p>{item.body}</p>
              <small>{new Date(item.created_at).toLocaleString("ru-RU")}</small>
            </div>
          </article>
        ))}
      </div>
      <h3>Каналы</h3>
      <div className="settings-checks">
        <label>
          <input
            type="checkbox"
            checked={value.channels.in_app}
            disabled={child}
            onChange={(e) =>
              onChange({ ...value, channels: { ...value.channels, in_app: e.target.checked } })
            }
          />
          Центр уведомлений
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.channels.push}
            disabled={child}
            onChange={(e) =>
              e.target.checked
                ? onPush()
                : onChange({ ...value, channels: { ...value.channels, push: false } })
            }
          />
          Web Push
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.channels.email}
            disabled={child}
            onChange={(e) =>
              onChange({ ...value, channels: { ...value.channels, email: e.target.checked } })
            }
          />
          Email
        </label>
      </div>
      {value.channels.email && (
        <label>
          Email
          <input
            type="email"
            value={value.email ?? ""}
            disabled={child}
            onChange={(e) => onChange({ ...value, email: e.target.value })}
          />
        </label>
      )}
      <h3>События</h3>
      <div className="settings-checks two-columns">
        {Object.entries(eventLabels).map(([key, label]) => (
          <label key={key}>
            <input
              type="checkbox"
              disabled={child}
              checked={value.event_rules[key] ?? true}
              onChange={(e) =>
                onChange({
                  ...value,
                  event_rules: { ...value.event_rules, [key]: e.target.checked },
                })
              }
            />
            {label}
          </label>
        ))}
      </div>
      <div className="form-columns">
        <label>
          Напомнить заранее, минут
          <input
            type="number"
            min="0"
            value={value.reminder_minutes}
            disabled={child}
            onChange={(e) => onChange({ ...value, reminder_minutes: Number(e.target.value) })}
          />
        </label>
        <label>
          Повтор, минут
          <input
            type="number"
            min="15"
            value={value.repeat_minutes ?? ""}
            disabled={child}
            onChange={(e) =>
              onChange({ ...value, repeat_minutes: e.target.value ? Number(e.target.value) : null })
            }
          />
        </label>
        <label>
          Тихие часы с
          <input
            type="time"
            value={value.quiet_start?.slice(0, 5) ?? ""}
            disabled={child}
            onChange={(e) => onChange({ ...value, quiet_start: e.target.value || null })}
          />
        </label>
        <label>
          до
          <input
            type="time"
            value={value.quiet_end?.slice(0, 5) ?? ""}
            disabled={child}
            onChange={(e) => onChange({ ...value, quiet_end: e.target.value || null })}
          />
        </label>
      </div>
      {child && <p className="permission-note">Критичные настройки ребёнка изменяет взрослый.</p>}
      <button className="primary-button" disabled={child} onClick={onSave}>
        Сохранить уведомления
      </button>
    </>
  );
}

function Appearance({
  value,
  onChange,
  onSave,
}: {
  value: UserPreference;
  onChange: (value: UserPreference) => void;
  onSave: () => void;
}) {
  return (
    <>
      <h2>Оформление</h2>
      <div className="form-grid">
        <label>
          Тема
          <select
            value={value.theme}
            onChange={(e) =>
              onChange({ ...value, theme: e.target.value as UserPreference["theme"] })
            }
          >
            <option value="system">Как в системе</option>
            <option value="light">Светлая</option>
            <option value="dark">Тёмная</option>
          </select>
        </label>
        <label>
          Размер текста
          <select
            value={value.font_scale}
            onChange={(e) =>
              onChange({ ...value, font_scale: e.target.value as UserPreference["font_scale"] })
            }
          >
            <option value="small">Компактный</option>
            <option value="normal">Обычный</option>
            <option value="large">Крупный</option>
          </select>
        </label>
        <label>
          Плотность
          <select
            value={value.density}
            onChange={(e) =>
              onChange({ ...value, density: e.target.value as UserPreference["density"] })
            }
          >
            <option value="comfortable">Удобная</option>
            <option value="compact">Плотная</option>
          </select>
        </label>
        <button className="primary-button" onClick={onSave}>
          Сохранить оформление
        </button>
      </div>
    </>
  );
}

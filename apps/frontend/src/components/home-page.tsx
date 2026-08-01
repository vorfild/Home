import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { Activity, Gauge, History, Plus, ShieldCheck, Wrench } from "lucide-react";

import {
  api,
  Equipment,
  HomeOverview,
  jsonBody,
  MaintenancePlan,
  Meter,
  MeterReading,
  RepairRecord,
  User,
} from "../lib/api";

type Tab = "overview" | "equipment" | "maintenance" | "meters" | "history";

const emptyOverview: HomeOverview = {
  meters_enabled: true,
  maintenance_due: [],
  warranties_expiring: [],
  meter_deadlines: [],
  equipment_attention: [],
};

export function HomePage({ currentUser }: { currentUser: User }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState(emptyOverview);
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [plans, setPlans] = useState<MaintenancePlan[]>([]);
  const [meters, setMeters] = useState<Meter[]>([]);
  const [history, setHistory] = useState<RepairRecord[]>([]);
  const [readings, setReadings] = useState<Record<string, MeterReading[]>>({});
  const [dialog, setDialog] = useState<"equipment" | "plan" | "meter" | "repair" | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const nextOverview = await api<HomeOverview>("/home/overview");
      const [nextEquipment, nextPlans, nextHistory] = await Promise.all([
        api<Equipment[]>("/home/equipment"),
        api<MaintenancePlan[]>("/home/maintenance"),
        api<RepairRecord[]>("/home/repairs"),
      ]);
      setOverview(nextOverview);
      setEquipment(nextEquipment);
      setPlans(nextPlans);
      setHistory(nextHistory);
      setMeters(nextOverview.meters_enabled ? await api<Meter[]>("/home/meters") : []);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить раздел");
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  async function loadReadings(meterId: string) {
    const items = await api<MeterReading[]>(`/home/meters/${meterId}/readings`);
    setReadings((current) => ({ ...current, [meterId]: items }));
  }

  async function toggleMeters() {
    await api("/home/meters/module", {
      method: "PUT",
      ...jsonBody({ enabled: !overview.meters_enabled }),
    });
    await load();
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Обзор" },
    { id: "equipment", label: "Оборудование" },
    { id: "maintenance", label: "Обслуживание" },
    ...(overview.meters_enabled ? [{ id: "meters" as const, label: "Счётчики" }] : []),
    { id: "history", label: "История ремонтов" },
  ];

  return (
    <main className="main-content module-page home-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Дом под присмотром</span>
          <h1>Дом и обслуживание</h1>
          <p>Оборудование, регламенты, гарантии и показания в одном месте.</p>
        </div>
        {currentUser.role === "admin" && (
          <button className="secondary-button" onClick={() => void toggleMeters()}>
            <Gauge /> {overview.meters_enabled ? "Скрыть счётчики" : "Включить счётчики"}
          </button>
        )}
      </header>
      {error && <p className="form-error">{error}</p>}
      <nav className="segmented-tabs home-tabs" aria-label="Разделы дома">
        {tabs.map((item) => (
          <button
            key={item.id}
            className={tab === item.id ? "is-active" : ""}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "overview" && <Overview data={overview} />}
      {tab === "equipment" && (
        <Collection title="Оборудование" onAdd={() => setDialog("equipment")}>
          {equipment.map((item) => (
            <article className="module-card equipment-card" key={item.id}>
              <Wrench />
              <div>
                <h3>{item.name}</h3>
                <p>{[item.category, item.location].filter(Boolean).join(" · ") || "Без категории"}</p>
                <span className={`status-pill ${item.condition}`}>{item.condition}</span>
              </div>
              {item.warranty_until && <small>Гарантия до {item.warranty_until}</small>}
            </article>
          ))}
        </Collection>
      )}
      {tab === "maintenance" && (
        <Collection title="Регламенты" onAdd={() => setDialog("plan")}>
          {plans.map((item) => (
            <article className="module-card maintenance-card" key={item.id}>
              <Activity />
              <div>
                <h3>{item.title}</h3>
                <p>Следующее обслуживание: {item.next_on}</p>
                <small>Каждые {item.interval_days} дней · {item.checklist.length} шагов</small>
              </div>
              {item.open_task_id && <span className="status-pill due">Дело создано</span>}
              <button
                className="secondary-button"
                onClick={async () => {
                  await api(`/home/maintenance/${item.id}/complete`, {
                    method: "POST",
                    ...jsonBody({ performed_on: new Date().toISOString().slice(0, 10) }),
                  });
                  await load();
                }}
              >
                Выполнено
              </button>
            </article>
          ))}
        </Collection>
      )}
      {tab === "meters" && overview.meters_enabled && (
        <Collection title="Счётчики" onAdd={() => setDialog("meter")}>
          {meters.map((item) => (
            <MeterCard
              key={item.id}
              meter={item}
              readings={readings[item.id]}
              onOpen={() => void loadReadings(item.id)}
              onSaved={load}
            />
          ))}
        </Collection>
      )}
      {tab === "history" && (
        <Collection title="Ремонты и сервис" onAdd={() => setDialog("repair")}>
          {history.map((item) => (
            <article className="module-card history-card" key={item.id}>
              <History />
              <div>
                <h3>{item.title}</h3>
                <p>{item.performed_on} · {item.record_type === "repair" ? "ремонт" : "обслуживание"}</p>
              </div>
              <small>{item.keep_forever ? "Хранится бессрочно" : "Хранится 2 года"}</small>
            </article>
          ))}
        </Collection>
      )}
      {dialog && (
        <CreateHomeDialog
          kind={dialog}
          equipment={equipment}
          onClose={() => setDialog(null)}
          onSaved={async () => {
            setDialog(null);
            await load();
          }}
        />
      )}
    </main>
  );
}

function Overview({ data }: { data: HomeOverview }) {
  const cards = [
    ["Ближайшее обслуживание", data.maintenance_due.length, Activity],
    ["Гарантии", data.warranties_expiring.length, ShieldCheck],
    ["Сроки показаний", data.meter_deadlines.length, Gauge],
    ["Требует внимания", data.equipment_attention.length, Wrench],
  ] as const;
  return (
    <section className="home-overview-grid">
      {cards.map(([title, count, Icon]) => (
        <article className="module-card overview-stat" key={title}>
          <Icon />
          <strong>{count}</strong>
          <span>{title}</span>
        </article>
      ))}
    </section>
  );
}

function Collection({ title, onAdd, children }: { title: string; onAdd: () => void; children: ReactNode }) {
  return (
    <section>
      <div className="section-title-row">
        <h2>{title}</h2>
        <button className="primary-button" onClick={onAdd}><Plus /> Добавить</button>
      </div>
      <div className="home-card-list">{children}</div>
    </section>
  );
}

function MeterCard({ meter, readings, onOpen, onSaved }: { meter: Meter; readings?: MeterReading[]; onOpen: () => void; onSaved: () => Promise<void> }) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = { value: Number(data.get("value")), read_on: data.get("read_on"), accept_decrease: true };
    await api(`/home/meters/${meter.id}/readings`, { method: "POST", ...jsonBody(body) });
    await onSaved();
    onOpen();
  }
  const points = readings ?? [];
  const max = Math.max(1, ...points.map((item) => Number(item.value)));
  return (
    <article className="module-card meter-card">
      <div><h3>{meter.meter_type}</h3><p>{meter.location || "Место не указано"}</p></div>
      <strong>{meter.last_value ?? "—"} {meter.unit}</strong>
      <button className="secondary-button" onClick={onOpen}>История и график</button>
      {readings && (
        <div className="meter-expanded">
          <div className="meter-chart" aria-label="График показаний">
            {points.map((item) => <i key={item.id} style={{ height: `${Math.max(8, Number(item.value) / max * 100)}%` }} title={`${item.read_on}: ${item.value}`} />)}
          </div>
          <form className="inline-form" onSubmit={(event) => void submit(event)}>
            <input name="value" type="number" step="0.0001" required placeholder="Новое показание" />
            <input name="read_on" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required />
            <button className="primary-button">Сохранить</button>
          </form>
        </div>
      )}
    </article>
  );
}

function CreateHomeDialog({ kind, equipment, onClose, onSaved }: { kind: "equipment" | "plan" | "meter" | "repair"; equipment: Equipment[]; onClose: () => void; onSaved: () => Promise<void> }) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const path = `/home/${kind === "plan" ? "maintenance" : kind === "repair" ? "repairs" : kind}`;
    let body: Record<string, unknown> = {};
    if (kind === "equipment") body = { name: data.get("name"), category: data.get("category") || null, location: data.get("location") || null, condition: "working" };
    if (kind === "plan") body = { title: data.get("name"), equipment_id: data.get("equipment_id") || null, interval_days: Number(data.get("interval_days")), next_on: data.get("date"), checklist: String(data.get("checklist") || "").split(",").map((x) => x.trim()).filter(Boolean) };
    if (kind === "meter") body = { meter_type: data.get("name"), unit: data.get("unit"), location: data.get("location") || null, next_submission_on: data.get("date") || null };
    if (kind === "repair") body = { title: data.get("name"), equipment_id: data.get("equipment_id") || null, performed_on: data.get("date"), comment: data.get("comment") || null, keep_forever: data.get("keep_forever") === "on" };
    await api(path, { method: "POST", ...jsonBody(body) });
    await onSaved();
  }
  return (
    <div className="modal-backdrop">
      <section className="modal-card" role="dialog" aria-modal="true">
        <h2>Новая запись</h2>
        <form className="form-grid" onSubmit={(event) => void submit(event)}>
          <label>Название<input name="name" required autoFocus /></label>
          {(kind === "plan" || kind === "repair") && <label>Оборудование<select name="equipment_id"><option value="">Без привязки</option>{equipment.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>}
          {kind === "equipment" && <><label>Категория<input name="category" /></label><label>Место<input name="location" /></label></>}
          {kind === "plan" && <><label>Периодичность, дней<input name="interval_days" type="number" min="1" defaultValue="30" required /></label><label>Следующая дата<input name="date" type="date" required /></label><label>Чек-лист через запятую<input name="checklist" /></label></>}
          {kind === "meter" && <><label>Единица<input name="unit" placeholder="кВт·ч" required /></label><label>Место<input name="location" /></label><label>Следующая передача<input name="date" type="date" /></label></>}
          {kind === "repair" && <><label>Дата работ<input name="date" type="date" required /></label><label>Комментарий<textarea name="comment" /></label><label className="check-label"><input name="keep_forever" type="checkbox" /> Хранить бессрочно</label></>}
          <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Отмена</button><button className="primary-button">Сохранить</button></div>
        </form>
      </section>
    </div>
  );
}

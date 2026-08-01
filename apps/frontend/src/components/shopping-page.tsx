import { Check, ChevronDown, Plus, ShoppingBag, WifiOff } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError, jsonBody, ShoppingItem, ShoppingList, User } from "../lib/api";
import { ru } from "../lib/i18n";
import {
  cachedShopping,
  cacheShopping,
  pendingShoppingCount,
  queueShopping,
  syncShoppingQueue,
} from "../lib/shopping-offline";

type View = "current" | "planned" | "history" | "proposals";
type Frequent = { name: string; category: string; unit: string; count: number };

function quantity(item: ShoppingItem): string {
  const numeric = Number(item.quantity);
  return `${Number.isInteger(numeric) ? numeric : numeric.toLocaleString("ru-RU")} ${item.unit}`;
}

export function ShoppingPage({ currentUser }: { currentUser: User }) {
  const [view, setView] = useState<View>("current");
  const [lists, setLists] = useState<ShoppingList[]>(cachedShopping);
  const [proposals, setProposals] = useState<ShoppingItem[]>([]);
  const [members, setMembers] = useState<User[]>([]);
  const [frequent, setFrequent] = useState<Frequent[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [completing, setCompleting] = useState<ShoppingList | null>(null);
  const [offline, setOffline] = useState(!navigator.onLine);
  const [pending, setPending] = useState(pendingShoppingCount);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      if (view === "proposals") {
        setProposals(await api<ShoppingItem[]>("/shopping/proposals"));
      } else {
        const loaded = await api<ShoppingList[]>(`/shopping/lists?view=${view}`);
        setLists(loaded);
        if (view !== "history") cacheShopping(loaded);
      }
      const [people, popular] = await Promise.all([
        api<User[]>("/family/members"),
        api<Frequent[]>("/shopping/frequent"),
      ]);
      setMembers(people);
      setFrequent(popular);
      setOffline(false);
      setError("");
    } catch (caught) {
      setOffline(!navigator.onLine);
      if (navigator.onLine) setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }, [view]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  useEffect(() => {
    async function online() {
      setOffline(false);
      setPending(await syncShoppingQueue());
      await load();
    }
    function offlineNow() {
      setOffline(true);
    }
    window.addEventListener("online", online);
    window.addEventListener("offline", offlineNow);
    return () => {
      window.removeEventListener("online", online);
      window.removeEventListener("offline", offlineNow);
    };
  }, [load]);

  async function toggle(list: ShoppingList, item: ShoppingItem) {
    const purchased = !item.purchased;
    setLists((all) =>
      all.map((candidate) =>
        candidate.id === list.id
          ? {
              ...candidate,
              items: candidate.items.map((value) =>
                value.id === item.id ? { ...value, purchased } : value,
              ),
            }
          : candidate,
      ),
    );
    if (!navigator.onLine) {
      queueShopping({ kind: "toggle", id: crypto.randomUUID(), itemId: item.id, purchased });
      setPending(pendingShoppingCount());
      return;
    }
    try {
      await api(`/shopping/items/${item.id}`, {
        method: "PATCH",
        ...jsonBody({ purchased }),
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
      await load();
    }
  }

  async function addItem(list: ShoppingList, payload: Record<string, unknown>) {
    const operationId = crypto.randomUUID();
    if (!navigator.onLine) {
      const optimistic: ShoppingItem = {
        id: `offline:${operationId}`,
        list_id: list.id,
        name: String(payload.name),
        quantity: String(payload.quantity ?? 1),
        unit: String(payload.unit ?? "шт."),
        category: String(payload.category ?? "другое"),
        note: null,
        added_by_id: currentUser.id,
        recipient_id: (payload.recipient_id as string | null) ?? null,
        purchased: false,
        photo_id: null,
        price: null,
        store: null,
        proposal_status: currentUser.role === "child" ? "pending" : "accepted",
        duplicate_warning: false,
      };
      setLists((all) =>
        all.map((candidate) =>
          candidate.id === list.id
            ? { ...candidate, items: [...candidate.items, optimistic] }
            : candidate,
        ),
      );
      queueShopping({ kind: "add", id: operationId, listId: list.id, payload });
      setPending(pendingShoppingCount());
      return;
    }
    const created = await api<ShoppingItem>(`/shopping/lists/${list.id}/items`, {
      method: "POST",
      ...jsonBody({ ...payload, client_operation_id: operationId }),
    });
    setLists((all) =>
      all.map((candidate) =>
        candidate.id === list.id
          ? { ...candidate, items: [...candidate.items, created] }
          : candidate,
      ),
    );
    if (created.duplicate_warning) setError(ru.shopping.duplicate);
  }

  async function decide(item: ShoppingItem, decision: "accept" | "reject") {
    await api(`/shopping/proposals/${item.id}/decision`, {
      method: "POST",
      ...jsonBody({ decision }),
    });
    setProposals((items) => items.filter((candidate) => candidate.id !== item.id));
  }

  const memberNames = useMemo(
    () => new Map(members.map((member) => [member.id, member.name])),
    [members],
  );

  const tabs: View[] =
    currentUser.role === "child"
      ? ["current", "planned", "history"]
      : ["current", "planned", "history", "proposals"];

  return (
    <main className="main-content module-page shopping-page">
      <header className="page-header">
        <div>
          <p className="mobile-brand">{ru.brand}</p>
          <h1>{ru.shopping.title}</h1>
          <p className="page-subtitle">{ru.shopping.description}</p>
        </div>
        {currentUser.role !== "child" && (
          <button className="primary-button" type="button" onClick={() => setShowCreate(true)}>
            <Plus aria-hidden="true" /> {ru.shopping.newList}
          </button>
        )}
      </header>
      {(offline || pending > 0) && (
        <p className="offline-banner">
          <WifiOff aria-hidden="true" />
          {offline ? ru.shopping.offline : `${ru.shopping.syncPending}: ${pending}`}
        </p>
      )}
      <div className="tabs" role="tablist">
        {tabs.map((item) => (
          <button
            key={item}
            role="tab"
            aria-selected={view === item}
            className={view === item ? "is-active" : ""}
            onClick={() => setView(item)}
          >
            {ru.shopping.views[item]}
          </button>
        ))}
      </div>
      {error && <p className="form-error">{error}</p>}
      {view === "proposals" ? (
        <section className="card module-list">
          {proposals.map((item) => (
            <article className="module-row" key={item.id}>
              <ShoppingBag aria-hidden="true" />
              <div className="module-row-copy">
                <strong>{item.name}</strong>
                <span>{quantity(item)}</span>
              </div>
              <div className="row-actions">
                <button onClick={() => void decide(item, "accept")}>{ru.shopping.accept}</button>
                <button onClick={() => void decide(item, "reject")}>{ru.shopping.reject}</button>
              </div>
            </article>
          ))}
          {proposals.length === 0 && <p className="empty-state">{ru.shopping.noProposals}</p>}
        </section>
      ) : (
        <section className="shopping-lists">
          {lists.map((list) => (
            <ShoppingListCard
              key={list.id}
              list={list}
              memberNames={memberNames}
              members={members}
              frequent={frequent}
              onToggle={toggle}
              onAdd={addItem}
              canManage={currentUser.role !== "child"}
              onComplete={() => setCompleting(list)}
            />
          ))}
          {lists.length === 0 && <p className="empty-state">{ru.shopping.empty}</p>}
        </section>
      )}
      {showCreate && (
        <CreateListDialog
          members={members}
          onClose={() => setShowCreate(false)}
          onCreated={(created) => {
            setLists((items) => [...items, created]);
            setShowCreate(false);
          }}
        />
      )}
      {completing && (
        <CompleteListDialog
          list={completing}
          targets={lists.filter(
            (candidate) => candidate.id !== completing.id && candidate.status !== "completed",
          )}
          onClose={() => setCompleting(null)}
          onCompleted={() => {
            setCompleting(null);
            void load();
          }}
        />
      )}
    </main>
  );
}

function ShoppingListCard({
  list,
  memberNames,
  members,
  frequent,
  onToggle,
  onAdd,
  canManage,
  onComplete,
}: {
  list: ShoppingList;
  memberNames: Map<string, string>;
  members: User[];
  frequent: Frequent[];
  onToggle: (list: ShoppingList, item: ShoppingItem) => Promise<void>;
  onAdd: (list: ShoppingList, payload: Record<string, unknown>) => Promise<void>;
  canManage: boolean;
  onComplete: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [recipient, setRecipient] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim()) return;
    await onAdd(list, { name: draft.trim(), recipient_id: recipient || null });
    setDraft("");
  }
  return (
    <article className="card shopping-list-card">
      <header>
        <div>
          <h2>{list.title}</h2>
          <span>
            {list.store ?? ru.shopping.anyStore}
            {list.scheduled_at
              ? ` · ${new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(list.scheduled_at))}`
              : ""}
          </span>
        </div>
        <div className="list-header-actions">
          <b>
            {list.items.filter((item) => item.purchased).length}/{list.items.length}
          </b>
          {canManage && list.status !== "completed" && (
            <button type="button" className="secondary-button" onClick={onComplete}>
              {ru.shopping.completeList}
            </button>
          )}
        </div>
      </header>
      <div className="shopping-items">
        {list.items.map((item) => {
          const extra = Boolean(item.note || item.photo_id || item.price || item.store);
          return (
            <div className={`shopping-item${item.purchased ? " is-complete" : ""}`} key={item.id}>
              <button
                className="task-checkbox"
                aria-label={`${ru.shopping.purchased}: ${item.name}`}
                aria-pressed={item.purchased}
                onClick={() => void onToggle(list, item)}
              >
                {item.purchased && <Check aria-hidden="true" />}
              </button>
              <strong>{item.name}</strong>
              <span>{quantity(item)}</span>
              <span>
                {item.recipient_id ? memberNames.get(item.recipient_id) : ru.shopping.common}
              </span>
              {extra && (
                <details>
                  <summary aria-label={ru.shopping.details}>
                    <ChevronDown aria-hidden="true" />
                  </summary>
                  <p>{[item.note, item.store, item.price].filter(Boolean).join(" · ")}</p>
                </details>
              )}
            </div>
          );
        })}
      </div>
      {list.status !== "completed" && (
        <form className="shopping-add" onSubmit={(event) => void submit(event)}>
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={ru.shopping.addItem}
          />
          <select
            value={recipient}
            onChange={(event) => setRecipient(event.target.value)}
            aria-label={ru.shopping.recipient}
          >
            <option value="">{ru.shopping.common}</option>
            {members.map((member) => (
              <option key={member.id} value={member.id}>
                {member.name}
              </option>
            ))}
          </select>
          <button type="submit">
            <Plus aria-hidden="true" />
          </button>
        </form>
      )}
      {frequent.length > 0 && list.status !== "completed" && (
        <div className="frequent-items" aria-label={ru.shopping.frequent}>
          {frequent.slice(0, 5).map((item) => (
            <button
              key={`${item.name}-${item.unit}`}
              onClick={() =>
                void onAdd(list, { name: item.name, category: item.category, unit: item.unit })
              }
            >
              + {item.name}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

function CreateListDialog({
  members,
  onClose,
  onCreated,
}: {
  members: User[];
  onClose: () => void;
  onCreated: (list: ShoppingList) => void;
}) {
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const scheduled = String(data.get("scheduled_at") ?? "");
    try {
      onCreated(
        await api<ShoppingList>("/shopping/lists", {
          method: "POST",
          ...jsonBody({
            title: data.get("title"),
            store: data.get("store") || null,
            scheduled_at: scheduled ? new Date(scheduled).toISOString() : null,
            responsible_id: data.get("responsible_id") || null,
          }),
        }),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : ru.common.error);
    }
  }
  return (
    <div className="modal-backdrop">
      <section className="modal-card" role="dialog" aria-modal="true">
        <h2>{ru.shopping.newList}</h2>
        <form className="form-grid" onSubmit={(event) => void submit(event)}>
          <label>
            {ru.shopping.listName}
            <input name="title" required autoFocus />
          </label>
          <label>
            {ru.shopping.store}
            <input name="store" />
          </label>
          <label>
            {ru.shopping.when}
            <input name="scheduled_at" type="datetime-local" />
          </label>
          <label>
            {ru.shopping.responsible}
            <select name="responsible_id">
              <option value="">{ru.family.nobody}</option>
              {members.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name}
                </option>
              ))}
            </select>
          </label>
          {error && <p className="form-error">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              {ru.common.cancel}
            </button>
            <button className="primary-button">{ru.common.save}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

function CompleteListDialog({
  list,
  targets,
  onClose,
  onCompleted,
}: {
  list: ShoppingList;
  targets: ShoppingList[];
  onClose: () => void;
  onCompleted: () => void;
}) {
  const [strategy, setStrategy] = useState<"keep" | "move" | "remove">("keep");
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await api(`/shopping/lists/${list.id}/complete`, {
        method: "POST",
        ...jsonBody({ unpurchased: strategy, target_list_id: strategy === "move" ? target : null }),
      });
      onCompleted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }
  return (
    <div className="modal-backdrop">
      <section className="modal-card" role="dialog" aria-modal="true">
        <h2>{ru.shopping.unpurchasedTitle}</h2>
        <p>{ru.shopping.unpurchasedText}</p>
        <form className="form-grid" onSubmit={(event) => void submit(event)}>
          <label>
            {ru.shopping.action}
            <select
              value={strategy}
              onChange={(event) => setStrategy(event.target.value as typeof strategy)}
            >
              <option value="keep">{ru.shopping.keep}</option>
              <option value="move">{ru.shopping.move}</option>
              <option value="remove">{ru.shopping.remove}</option>
            </select>
          </label>
          {strategy === "move" && (
            <label>
              {ru.shopping.targetList}
              <select value={target} onChange={(event) => setTarget(event.target.value)} required>
                <option value="">{ru.shopping.chooseList}</option>
                {targets.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.title}
                  </option>
                ))}
              </select>
            </label>
          )}
          {error && <p className="form-error">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              {ru.common.cancel}
            </button>
            <button className="primary-button">{ru.shopping.completeList}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

import {
  Box,
  ChevronRight,
  Clock,
  Folder,
  Move,
  Plus,
  QrCode,
  Search,
  WifiOff,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";

import {
  api,
  jsonBody,
  StorageContents,
  StorageItem,
  StorageNode,
  StorageQr,
  User,
} from "../lib/api";
import { ru } from "../lib/i18n";
import { cachedStorageSection, cacheStorageSection } from "../lib/storage-offline";

const emptyContents: StorageContents = { node: null, children: [], items: [] };

export function StoragePage({
  currentUser,
  initialQrToken,
}: {
  currentUser: User;
  initialQrToken?: string;
}) {
  const [tree, setTree] = useState<StorageNode[]>([]);
  const [members, setMembers] = useState<User[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [contents, setContents] = useState<StorageContents>(emptyContents);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"descendants" | "level">("descendants");
  const [searchItems, setSearchItems] = useState<StorageItem[] | null>(null);
  const [showNode, setShowNode] = useState(false);
  const [showItem, setShowItem] = useState(false);
  const [qr, setQr] = useState<StorageQr | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [bulkKind, setBulkKind] = useState<
    "" | "move" | "category" | "owner" | "timer" | "archive"
  >("");
  const [offline, setOffline] = useState(!navigator.onLine);
  const [error, setError] = useState("");

  const loadTree = useCallback(async () => {
    try {
      setTree(await api<StorageNode[]>("/storage/tree"));
    } catch (caught) {
      if (navigator.onLine) setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }, []);

  const openNode = useCallback(async (nodeId: string | null) => {
    setCurrentId(nodeId);
    setSearchItems(null);
    setSelected([]);
    try {
      const next = await api<StorageContents>(
        nodeId ? `/storage/nodes/${nodeId}/contents` : "/storage/root",
      );
      setContents(next);
      if (nodeId) cacheStorageSection(nodeId, next);
      setOffline(false);
      setError("");
    } catch (caught) {
      const cached = nodeId ? cachedStorageSection(nodeId) : null;
      if (cached) {
        setContents(cached);
        setOffline(true);
      } else {
        setError(caught instanceof Error ? caught.message : ru.common.error);
      }
    }
  }, []);

  useEffect(() => {
    async function boot() {
      await Promise.all([
        loadTree(),
        api<User[]>("/family/members")
          .then(setMembers)
          .catch(() => undefined),
      ]);
      if (initialQrToken) {
        try {
          const qrContents = await api<StorageContents>(`/storage/qr/${initialQrToken}`);
          setContents(qrContents);
          setCurrentId(qrContents.node?.id ?? null);
          return;
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : ru.common.error);
        }
      }
      await openNode(null);
    }
    void boot();
  }, [initialQrToken, loadTree, openNode]);

  async function search(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || offline) return;
    const params = new URLSearchParams({ q: query.trim(), scope });
    if (currentId) params.set("node_id", currentId);
    const result = await api<{ items: StorageItem[] }>(`/storage/search?${params}`);
    setSearchItems(result.items);
  }

  async function usedToday(item: StorageItem) {
    const updated = await api<StorageItem>(`/storage/items/${item.id}/used-today`, {
      method: "POST",
    });
    setContents((value) => ({
      ...value,
      items: value.items.map((candidate) => (candidate.id === item.id ? updated : candidate)),
    }));
  }

  async function createQr(regenerate = false) {
    if (!currentId || offline) return;
    const result = await api<StorageQr>(
      `/storage/nodes/${currentId}/qr${regenerate ? "/regenerate" : ""}`,
      { method: "POST" },
    );
    setQr(result);
    await loadTree();
  }

  async function bulkMove(target: string) {
    await api("/storage/bulk", {
      method: "POST",
      ...jsonBody({ item_ids: selected, action: "move", node_id: target }),
    });
    await openNode(currentId);
  }

  async function bulkValue(action: "category" | "timer" | "archive", value?: string | number) {
    const payload: Record<string, unknown> = { item_ids: selected, action };
    if (action === "category") payload.category = value;
    if (action === "timer" && value) payload.timer_days = value;
    await api("/storage/bulk", { method: "POST", ...jsonBody(payload) });
    await openNode(currentId);
    setBulkKind("");
  }

  function chooseBulk(action: typeof bulkKind) {
    setBulkKind(action);
    if (action === "category") {
      const category = window.prompt(ru.storage.categoryPrompt);
      if (category) void bulkValue("category", category);
    } else if (action === "timer") {
      const raw = window.prompt(ru.storage.extendPrompt, "30");
      const days = Number(raw);
      if (raw && Number.isInteger(days) && days > 0) {
        void bulkValue("timer", days);
      }
    } else if (action === "archive" && window.confirm(ru.storage.archiveConfirm)) {
      void bulkValue("archive");
    }
  }

  async function bulkOwner(ownerId: string) {
    await api("/storage/bulk", {
      method: "POST",
      ...jsonBody({ item_ids: selected, action: "owner", owner_id: ownerId }),
    });
    await openNode(currentId);
    setBulkKind("");
  }

  async function moveItem(item: StorageItem, target: string) {
    await api(`/storage/items/${item.id}`, {
      method: "PATCH",
      ...jsonBody({ node_id: target }),
    });
    await openNode(currentId);
  }

  async function extendTimer(item: StorageItem) {
    const raw = window.prompt(ru.storage.extendPrompt, "30");
    if (!raw) return;
    const days = Number(raw);
    if (!Number.isInteger(days) || days < 1) return;
    const updated = await api<StorageItem>(`/storage/items/${item.id}/extend`, {
      method: "POST",
      ...jsonBody({ days }),
    });
    setContents((value) => ({
      ...value,
      items: value.items.map((candidate) => (candidate.id === item.id ? updated : candidate)),
    }));
  }

  const visibleItems = searchItems ?? contents.items;
  const currentPath = contents.node?.path ?? [];
  const canEdit = currentUser.role !== "child" && !offline;

  return (
    <main className="main-content module-page storage-page">
      <header className="page-header">
        <div>
          <p className="mobile-brand">{ru.brand}</p>
          <h1>{ru.storage.title}</h1>
          <p className="page-subtitle">{ru.storage.description}</p>
        </div>
        {canEdit && (
          <div className="header-actions">
            <button className="secondary-button" onClick={() => setShowNode(true)}>
              <Folder aria-hidden="true" /> {ru.storage.addSection}
            </button>
            {currentId && (
              <button className="primary-button" onClick={() => setShowItem(true)}>
                <Plus aria-hidden="true" /> {ru.storage.addItem}
              </button>
            )}
          </div>
        )}
      </header>
      {offline && (
        <p className="offline-banner">
          <WifiOff /> {ru.storage.offline}
        </p>
      )}
      {error && <p className="form-error">{error}</p>}
      <form className="storage-search" onSubmit={(event) => void search(event)}>
        <Search aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={ru.storage.search}
          disabled={offline}
        />
        <select
          value={scope}
          onChange={(event) => setScope(event.target.value as typeof scope)}
          disabled={!currentId || offline}
        >
          <option value="descendants">{ru.storage.hereBelow}</option>
          <option value="level">{ru.storage.onlyLevel}</option>
        </select>
        <button>{ru.storage.find}</button>
      </form>
      <nav className="breadcrumbs" aria-label={ru.storage.path}>
        <button onClick={() => void openNode(null)}>{ru.storage.root}</button>
        {currentPath.map((part) => (
          <span key={part.id}>
            <ChevronRight />
            <button onClick={() => void openNode(part.id)}>{part.name}</button>
          </span>
        ))}
      </nav>
      <section className="storage-layout">
        <aside className="card storage-tree" aria-label={ru.storage.tree}>
          <button className={!currentId ? "is-active" : ""} onClick={() => void openNode(null)}>
            {ru.storage.root}
          </button>
          {tree.map((node) => (
            <button
              key={node.id}
              className={node.id === currentId ? "is-active" : ""}
              style={{ paddingLeft: `${14 + (node.path.length - 1) * 18}px` }}
              onClick={() => void openNode(node.id)}
            >
              <Folder aria-hidden="true" /> {node.name}
            </button>
          ))}
        </aside>
        <section className="storage-content">
          {contents.children.length > 0 && !searchItems && (
            <div className="storage-sections">
              {contents.children.map((node) => (
                <button
                  className="card storage-section-card"
                  key={node.id}
                  onClick={() => void openNode(node.id)}
                >
                  <Folder aria-hidden="true" />
                  <strong>{node.name}</strong>
                  <span>{node.node_type}</span>
                </button>
              ))}
            </div>
          )}
          {currentId && canEdit && !searchItems && (
            <div className="storage-tools">
              <button className="secondary-button" onClick={() => void createQr(false)}>
                <QrCode /> {contents.node?.has_qr ? ru.storage.openQr : ru.storage.createQr}
              </button>
            </div>
          )}
          {selected.length > 0 && canEdit && (
            <div className="bulk-toolbar">
              <Move />
              <span>
                {ru.storage.selected}: {selected.length}
              </span>
              <select
                value={bulkKind}
                onChange={(event) => chooseBulk(event.target.value as typeof bulkKind)}
              >
                <option value="">{ru.storage.bulkAction}</option>
                <option value="move">{ru.storage.move}</option>
                <option value="category">{ru.storage.changeCategory}</option>
                <option value="owner">{ru.storage.changeOwner}</option>
                <option value="timer">{ru.storage.setTimer}</option>
                <option value="archive">{ru.storage.archive}</option>
              </select>
              {bulkKind === "move" && (
                <select
                  defaultValue=""
                  onChange={(event) => event.target.value && void bulkMove(event.target.value)}
                >
                  <option value="">{ru.storage.chooseTarget}</option>
                  {tree
                    .filter((node) => node.id !== currentId)
                    .map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.path.map((part) => part.name).join(" / ")}
                      </option>
                    ))}
                </select>
              )}
              {bulkKind === "owner" && (
                <select
                  defaultValue=""
                  onChange={(event) => event.target.value && void bulkOwner(event.target.value)}
                >
                  <option value="">{ru.storage.chooseOwner}</option>
                  {members.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}
          <div className="storage-items-grid">
            {visibleItems.map((item) => (
              <StorageItemCard
                key={item.id}
                item={item}
                selectable={canEdit}
                canEdit={canEdit}
                actionsEnabled={!offline}
                nodes={tree}
                selected={selected.includes(item.id)}
                onSelect={(checked) =>
                  setSelected((items) =>
                    checked ? [...items, item.id] : items.filter((id) => id !== item.id),
                  )
                }
                onUsed={() => void usedToday(item)}
                onMove={(target) => void moveItem(item, target)}
                onExtend={() => void extendTimer(item)}
              />
            ))}
          </div>
          {contents.children.length === 0 && visibleItems.length === 0 && (
            <p className="empty-state">{ru.storage.empty}</p>
          )}
        </section>
      </section>
      {showNode && (
        <CreateNodeDialog
          parentId={currentId}
          onClose={() => setShowNode(false)}
          onCreated={() => {
            setShowNode(false);
            void loadTree();
            void openNode(currentId);
          }}
        />
      )}
      {showItem && currentId && (
        <CreateItemDialog
          nodeId={currentId}
          members={[]}
          onClose={() => setShowItem(false)}
          onCreated={() => {
            setShowItem(false);
            void openNode(currentId);
          }}
        />
      )}
      {qr && (
        <QrDialog
          qr={qr}
          nodeName={contents.node?.name ?? ""}
          onRegenerate={() => void createQr(true)}
          onClose={() => setQr(null)}
        />
      )}
    </main>
  );
}

function StorageItemCard({
  item,
  selectable,
  canEdit,
  actionsEnabled,
  nodes,
  selected,
  onSelect,
  onUsed,
  onMove,
  onExtend,
}: {
  item: StorageItem;
  selectable: boolean;
  canEdit: boolean;
  actionsEnabled: boolean;
  nodes: StorageNode[];
  selected: boolean;
  onSelect: (checked: boolean) => void;
  onUsed: () => void;
  onMove: (target: string) => void;
  onExtend: () => void;
}) {
  return (
    <article
      className={`card storage-item-card${item.review_status === "decision_required" ? " needs-decision" : ""}`}
    >
      {selectable && (
        <input
          type="checkbox"
          checked={selected}
          onChange={(event) => onSelect(event.target.checked)}
          aria-label={`${ru.storage.select} ${item.name}`}
        />
      )}
      <div className="item-photo-placeholder">
        <Box aria-hidden="true" />
      </div>
      <h3>{item.name}</h3>
      <p>
        {item.quantity
          ? `${item.quantity} ${item.unit ?? ""}`
          : (item.category ?? ru.storage.noCategory)}
      </p>
      <p>
        <Clock aria-hidden="true" />{" "}
        {item.review_status === "decision_required"
          ? ru.storage.decisionRequired
          : item.last_used_at
            ? `${ru.storage.used}: ${item.last_used_at}`
            : ru.storage.notUsed}
      </p>
      <details>
        <summary>{ru.storage.details}</summary>
        {item.description && <p>{item.description}</p>}
        <p>{item.path.map((part) => part.name).join(" / ")}</p>
        <button className="secondary-button" onClick={onUsed} disabled={!actionsEnabled}>
          {ru.storage.usedToday}
        </button>
        {canEdit && (
          <div className="item-card-actions">
            <button className="secondary-button" onClick={onExtend}>
              {ru.storage.extend}
            </button>
            <select
              defaultValue=""
              onChange={(event) => event.target.value && onMove(event.target.value)}
            >
              <option value="">{ru.storage.move}</option>
              {nodes
                .filter((node) => node.id !== item.node_id)
                .map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.path.map((part) => part.name).join(" / ")}
                  </option>
                ))}
            </select>
          </div>
        )}
      </details>
    </article>
  );
}

function CreateNodeDialog({
  parentId,
  onClose,
  onCreated,
}: {
  parentId: string | null;
  onClose: () => void;
  onCreated: () => void;
}) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await api("/storage/nodes", {
      method: "POST",
      ...jsonBody({
        name: data.get("name"),
        node_type: data.get("node_type"),
        parent_id: parentId,
      }),
    });
    onCreated();
  }
  return (
    <div className="modal-backdrop">
      <section className="modal-card" role="dialog" aria-modal="true">
        <h2>{ru.storage.addSection}</h2>
        <form className="form-grid" onSubmit={(event) => void submit(event)}>
          <label>
            {ru.storage.name}
            <input name="name" required autoFocus />
          </label>
          <label>
            {ru.storage.type}
            <select name="node_type">
              {ru.storage.nodeTypes.map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
          </label>
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

function CreateItemDialog({
  nodeId,
  onClose,
  onCreated,
}: {
  nodeId: string;
  members: User[];
  onClose: () => void;
  onCreated: () => void;
}) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const review = String(data.get("review_at") ?? "");
    await api("/storage/items", {
      method: "POST",
      ...jsonBody({
        name: data.get("name"),
        node_id: nodeId,
        category: data.get("category") || null,
        quantity: data.get("quantity") || null,
        unit: data.get("unit") || null,
        description: data.get("description") || null,
        tags: String(data.get("tags") ?? "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        review_at: review ? new Date(review).toISOString() : null,
      }),
    });
    onCreated();
  }
  return (
    <div className="modal-backdrop">
      <section className="modal-card wide-modal" role="dialog" aria-modal="true">
        <h2>{ru.storage.addItem}</h2>
        <form className="form-grid" onSubmit={(event) => void submit(event)}>
          <label>
            {ru.storage.name}
            <input name="name" required autoFocus />
          </label>
          <div className="form-columns">
            <label>
              {ru.storage.category}
              <input name="category" />
            </label>
            <label>
              {ru.storage.quantity}
              <input name="quantity" type="number" min="0.001" step="0.001" />
            </label>
            <label>
              {ru.storage.unit}
              <input name="unit" />
            </label>
            <label>
              {ru.storage.reviewAt}
              <input name="review_at" type="datetime-local" />
            </label>
          </div>
          <label>
            {ru.storage.tags}
            <input name="tags" />
          </label>
          <label>
            {ru.storage.descriptionField}
            <textarea name="description" />
          </label>
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

function QrDialog({
  qr,
  nodeName,
  onRegenerate,
  onClose,
}: {
  qr: StorageQr;
  nodeName: string;
  onRegenerate: () => void;
  onClose: () => void;
}) {
  const [image, setImage] = useState("");
  useEffect(() => {
    void QRCode.toDataURL(`${window.location.origin}${qr.path}`, { width: 360, margin: 2 }).then(
      setImage,
    );
  }, [qr]);
  return (
    <div className="modal-backdrop">
      <section className="modal-card qr-dialog" role="dialog" aria-modal="true">
        <h2>{nodeName}</h2>
        {image && <img src={image} alt={`${ru.storage.qrFor} ${nodeName}`} />}
        <p>
          {window.location.origin}
          {qr.path}
        </p>
        <div className="modal-actions">
          <button className="secondary-button" onClick={onRegenerate}>
            {ru.storage.regenerateQr}
          </button>
          <a className="primary-button" href={image} download={`qr-${nodeName}.png`}>
            {ru.storage.downloadQr}
          </a>
          <button className="secondary-button" onClick={onClose}>
            {ru.common.close}
          </button>
        </div>
      </section>
    </div>
  );
}

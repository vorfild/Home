import {
  CalendarOff,
  Check,
  Copy,
  KeyRound,
  Laptop,
  Plus,
  Shield,
  UserRound,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { api, FamilyStats, jsonBody, Role, User, UserCreated } from "../lib/api";
import { ru } from "../lib/i18n";

type Props = {
  currentUser: User;
  tabletTrusted: boolean;
  onTabletRegistered: () => void;
  onEnterTablet: () => void;
};

const roleLabels: Record<Role, string> = {
  admin: ru.family.admin,
  adult: ru.family.adult,
  child: ru.family.child,
};

function initial(name: string) {
  return name.trim().slice(0, 1).toUpperCase();
}

function Modal({
  children,
  onClose,
  label,
}: {
  children: React.ReactNode;
  onClose: () => void;
  label: string;
}) {
  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section className="modal-card" role="dialog" aria-modal="true" aria-label={label}>
        <button
          className="modal-close"
          type="button"
          aria-label={ru.common.close}
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </button>
        {children}
      </section>
    </div>
  );
}

function CreateMember({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (result: UserCreated) => void;
}) {
  const [form, setForm] = useState({
    name: "",
    login: "",
    role: "adult" as "adult" | "child",
    color: "#8DB8A8",
    child_must_change_password: false,
  });
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      onCreated(await api<UserCreated>("/family/members", { method: "POST", ...jsonBody(form) }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }

  return (
    <Modal label={ru.family.addTitle} onClose={onClose}>
      <h2>{ru.family.addTitle}</h2>
      <form className="form-stack" onSubmit={submit}>
        <label>
          <span>{ru.family.name}</span>
          <input
            autoFocus
            required
            maxLength={100}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
        </label>
        <label>
          <span>{ru.family.login}</span>
          <input
            required
            minLength={3}
            pattern="[A-Za-z0-9._-]+"
            autoCapitalize="none"
            value={form.login}
            onChange={(event) => setForm({ ...form, login: event.target.value })}
          />
        </label>
        <label>
          <span>{ru.family.role}</span>
          <select
            value={form.role}
            onChange={(event) =>
              setForm({ ...form, role: event.target.value as "adult" | "child" })
            }
          >
            <option value="adult">{ru.family.adult}</option>
            <option value="child">{ru.family.child}</option>
          </select>
        </label>
        <label>
          <span>{ru.family.color}</span>
          <input
            className="color-input"
            type="color"
            value={form.color}
            onChange={(event) => setForm({ ...form, color: event.target.value })}
          />
        </label>
        {form.role === "child" && (
          <label className="check-row">
            <input
              type="checkbox"
              checked={form.child_must_change_password}
              onChange={(event) =>
                setForm({ ...form, child_must_change_password: event.target.checked })
              }
            />
            <span>{ru.family.childChange}</span>
          </label>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="form-actions">
          <button className="secondary-button" type="button" onClick={onClose}>
            {ru.common.cancel}
          </button>
          <button className="primary-button" type="submit">
            {ru.family.create}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function TemporaryPassword({ password, onClose }: { password: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(password);
    setCopied(true);
  }
  return (
    <Modal label={ru.family.temporaryTitle} onClose={onClose}>
      <span className="auth-icon">
        <KeyRound aria-hidden="true" />
      </span>
      <h2>{ru.family.temporaryTitle}</h2>
      <p className="form-intro">{ru.family.temporaryText}</p>
      <code className="temporary-password">{password}</code>
      <button className="primary-button wide-button" type="button" onClick={copy}>
        {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {copied ? ru.family.copied : ru.family.copy}
      </button>
    </Modal>
  );
}

function MemberCard({
  member,
  members,
  currentUser,
  onChanged,
  onPassword,
  stats,
}: {
  member: User;
  members: User[];
  currentUser: User;
  onChanged: () => void;
  onPassword: (value: string) => void;
  stats?: FamilyStats;
}) {
  const [expanded, setExpanded] = useState(false);
  const [pin, setPin] = useState("");
  const [absence, setAbsence] = useState({
    starts_on: "",
    ends_on: "",
    substitute_user_id: "",
    note: "",
  });
  const [message, setMessage] = useState("");
  const isAdmin = currentUser.role === "admin";

  async function action(callback: () => Promise<unknown>) {
    setMessage("");
    try {
      await callback();
      onChanged();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : ru.common.error);
    }
  }

  async function resetPassword() {
    if (!window.confirm(ru.family.resetConfirm)) return;
    setMessage("");
    try {
      const result = await api<{ temporary_password: string }>(
        `/family/members/${member.id}/reset-password`,
        { method: "POST" },
      );
      onPassword(result.temporary_password);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : ru.common.error);
    }
  }

  return (
    <article className={`member-card${member.is_active ? "" : " is-disabled"}`}>
      <div className="member-summary">
        <span className="avatar member-avatar" style={{ background: member.color }}>
          {initial(member.name)}
        </span>
        <div className="member-copy">
          <h2>{member.name}</h2>
          <p>
            @{member.login} · {roleLabels[member.role]}
          </p>
        </div>
        <span className={`status-pill${member.active_absence ? " is-away" : ""}`}>
          {member.active_absence
            ? ru.family.away
            : member.is_active
              ? ru.family.active
              : ru.family.disabled}
        </span>
        {isAdmin && (
          <button
            className="secondary-button compact-button"
            type="button"
            onClick={() => setExpanded(!expanded)}
          >
            {ru.family.manage}
          </button>
        )}
      </div>
      {member.active_absence && (
        <div className="absence-banner">
          <CalendarOff aria-hidden="true" />
          <span>
            {member.active_absence.starts_on} — {member.active_absence.ends_on}
            {member.active_absence.note ? ` · ${member.active_absence.note}` : ""}
          </span>
        </div>
      )}
      {stats && (
        <div className="member-stats" aria-label="Сводка участника">
          <span>
            <strong>{stats.today_tasks}</strong> сегодня
          </span>
          <span>
            <strong>{stats.overdue_tasks}</strong> просрочено
          </span>
          <span>
            <strong>{stats.queue_tasks}</strong> очередь
          </span>
          <span>
            <strong>{stats.awaiting_review}</strong> проверка
          </span>
          <span>
            <strong>{stats.pending_requests}</strong> запросы
          </span>
        </div>
      )}
      {expanded && (
        <div className="member-management">
          <div className="management-actions">
            <button type="button" onClick={() => void resetPassword()}>
              {ru.family.reset}
            </button>
            <button
              type="button"
              onClick={() =>
                void action(() =>
                  api(`/family/members/${member.id}`, {
                    method: "PATCH",
                    ...jsonBody({ is_active: !member.is_active }),
                  }),
                )
              }
              disabled={member.id === currentUser.id}
            >
              {member.is_active ? ru.family.disable : ru.family.enable}
            </button>
            <button
              type="button"
              onClick={() =>
                window.confirm(ru.family.revokeConfirm) &&
                void action(() =>
                  api(`/family/members/${member.id}/sessions/revoke`, { method: "POST" }),
                )
              }
            >
              {ru.family.revoke}
            </button>
          </div>
          <div className="management-grid">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void action(() =>
                  api(`/family/members/${member.id}/pin`, { method: "PUT", ...jsonBody({ pin }) }),
                ).then(() => setPin(""));
              }}
            >
              <h3>{ru.family.pin}</h3>
              <div className="inline-form">
                <input
                  aria-label={ru.family.pin}
                  inputMode="numeric"
                  type="password"
                  pattern="\d{4,6}"
                  maxLength={6}
                  placeholder={ru.family.pinPlaceholder}
                  value={pin}
                  onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))}
                  required
                />
                <button className="secondary-button" type="submit">
                  {ru.family.setPin}
                </button>
              </div>
            </form>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void action(() =>
                  api(`/family/members/${member.id}/absences`, {
                    method: "POST",
                    ...jsonBody({
                      ...absence,
                      substitute_user_id: absence.substitute_user_id || null,
                      note: absence.note || null,
                    }),
                  }),
                );
              }}
            >
              <h3>{ru.family.absence}</h3>
              <div className="absence-fields">
                <label>
                  <span>{ru.family.from}</span>
                  <input
                    type="date"
                    required
                    value={absence.starts_on}
                    onChange={(event) => setAbsence({ ...absence, starts_on: event.target.value })}
                  />
                </label>
                <label>
                  <span>{ru.family.through}</span>
                  <input
                    type="date"
                    required
                    value={absence.ends_on}
                    onChange={(event) => setAbsence({ ...absence, ends_on: event.target.value })}
                  />
                </label>
              </div>
              <label>
                <span>{ru.family.substitute}</span>
                <select
                  value={absence.substitute_user_id}
                  onChange={(event) =>
                    setAbsence({ ...absence, substitute_user_id: event.target.value })
                  }
                >
                  <option value="">{ru.family.nobody}</option>
                  {members
                    .filter((candidate) => candidate.id !== member.id && candidate.is_active)
                    .map((candidate) => (
                      <option value={candidate.id} key={candidate.id}>
                        {candidate.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                <span>{ru.family.note}</span>
                <input
                  maxLength={300}
                  value={absence.note}
                  onChange={(event) => setAbsence({ ...absence, note: event.target.value })}
                />
              </label>
              <button className="secondary-button" type="submit">
                {ru.family.setAbsence}
              </button>
            </form>
          </div>
          {message && (
            <p className="inline-message" role="status">
              {message}
            </p>
          )}
        </div>
      )}
    </article>
  );
}

export function FamilyPage({
  currentUser,
  tabletTrusted,
  onTabletRegistered,
  onEnterTablet,
}: Props) {
  const [members, setMembers] = useState<User[]>([]);
  const [stats, setStats] = useState<FamilyStats[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const nextMembers = await api<User[]>("/family/members");
      const nextStats = await api<FamilyStats[]>("/family/summary").catch(() => []);
      setMembers(nextMembers);
      setStats(nextStats);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }, []);
  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  async function registerTablet() {
    try {
      await api("/family/tablets", { method: "POST", ...jsonBody({ name: ru.family.tabletName }) });
      onTabletRegistered();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }

  return (
    <main className="main-content family-page">
      <header className="family-header">
        <div>
          <p className="mobile-brand">{ru.brand}</p>
          <p className="eyebrow">{ru.family.eyebrow}</p>
          <h1>{ru.family.title}</h1>
          <p>{ru.family.text}</p>
        </div>
        {currentUser.role === "admin" && (
          <button className="primary-button" type="button" onClick={() => setShowCreate(true)}>
            <Plus aria-hidden="true" />
            {ru.family.add}
          </button>
        )}
      </header>
      {currentUser.role === "admin" && (
        <section className="tablet-card card">
          <span className="tablet-card-icon">
            <Laptop aria-hidden="true" />
          </span>
          <div>
            <h2>{ru.family.tabletName}</h2>
            <p>{tabletTrusted ? ru.family.tabletReady : ru.tablet.text}</p>
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={() => void (tabletTrusted ? onEnterTablet() : registerTablet())}
          >
            {tabletTrusted ? ru.family.enterTablet : ru.family.registerTablet}
          </button>
        </section>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <section className="members-list" aria-label={ru.family.title}>
        {members.length === 0 && !error && (
          <p className="empty-state">
            <UserRound aria-hidden="true" />
            {ru.family.noMembers}
          </p>
        )}
        {members.map((member) => (
          <MemberCard
            key={member.id}
            member={member}
            members={members}
            currentUser={currentUser}
            onChanged={() => void load()}
            onPassword={setTemporaryPassword}
            stats={stats.find((item) => item.user_id === member.id)}
          />
        ))}
      </section>
      <footer className="permission-note">
        <Shield aria-hidden="true" />
        {currentUser.role === "admin" ? ru.family.admin : roleLabels[currentUser.role]}
      </footer>
      {showCreate && (
        <CreateMember
          onClose={() => setShowCreate(false)}
          onCreated={(result) => {
            setShowCreate(false);
            setTemporaryPassword(result.temporary_password);
            void load();
          }}
        />
      )}
      {temporaryPassword && (
        <TemporaryPassword password={temporaryPassword} onClose={() => setTemporaryPassword("")} />
      )}
    </main>
  );
}

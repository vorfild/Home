import { ArrowLeft, KeyRound, LogIn, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { api, AuthResponse, jsonBody, User } from "../lib/api";
import { ru } from "../lib/i18n";

type LoginProps = {
  tabletAvailable: boolean;
  onAuthenticated: (auth: AuthResponse) => void;
  onTablet: () => void;
};

export function LoginScreen({ tabletAvailable, onAuthenticated, onTablet }: LoginProps) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<AuthResponse>("/auth/login", {
        method: "POST",
        ...jsonBody({ login, password }),
      });
      onAuthenticated(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="centered-auth">
      <div className="login-brand">{ru.brand}</div>
      <form className="auth-card login-card" onSubmit={submit}>
        <span className="auth-icon">
          <ShieldCheck aria-hidden="true" />
        </span>
        <h1>{ru.auth.title}</h1>
        <p className="form-intro">{ru.auth.text}</p>
        <div className="form-stack">
          <label>
            <span>{ru.auth.login}</span>
            <input
              autoFocus
              value={login}
              onChange={(event) => setLogin(event.target.value)}
              autoCapitalize="none"
              autoComplete="username"
              required
            />
          </label>
          <label>
            <span>{ru.auth.password}</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="primary-button wide-button" type="submit" disabled={busy}>
          <LogIn aria-hidden="true" /> {ru.auth.signIn}
        </button>
        {tabletAvailable && (
          <button className="text-button" type="button" onClick={onTablet}>
            {ru.auth.tablet}
          </button>
        )}
      </form>
    </main>
  );
}

export function ChangePasswordScreen({
  onAuthenticated,
}: {
  onAuthenticated: (auth: AuthResponse) => void;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const result = await api<AuthResponse>("/auth/change-password", {
        method: "POST",
        ...jsonBody({ current_password: currentPassword, new_password: newPassword }),
      });
      onAuthenticated(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }

  return (
    <main className="centered-auth">
      <form className="auth-card login-card" onSubmit={submit}>
        <span className="auth-icon">
          <KeyRound aria-hidden="true" />
        </span>
        <h1>{ru.auth.changeTitle}</h1>
        <p className="form-intro">{ru.auth.changeText}</p>
        <div className="form-stack">
          <label>
            <span>{ru.auth.currentPassword}</span>
            <input
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              required
            />
          </label>
          <label>
            <span>{ru.auth.newPassword}</span>
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              minLength={12}
              required
            />
            <small>{ru.setup.passwordHint}</small>
          </label>
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="primary-button wide-button" type="submit">
          {ru.auth.change}
        </button>
      </form>
    </main>
  );
}

type TabletProps = {
  onAuthenticated: (auth: AuthResponse) => void;
  onBack: () => void;
};

export function TabletScreen({ onAuthenticated, onBack }: TabletProps) {
  const [users, setUsers] = useState<User[]>([]);
  const [selected, setSelected] = useState<User | null>(null);
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<User[]>("/tablet/users")
      .then(setUsers)
      .catch((caught: Error) => setError(caught.message));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setError("");
    try {
      const auth = await api<AuthResponse>("/tablet/login", {
        method: "POST",
        ...jsonBody({ user_id: selected.id, pin }),
      });
      onAuthenticated(auth);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }

  return (
    <main className="tablet-layout">
      <button className="text-button tablet-back" type="button" onClick={onBack}>
        <ArrowLeft aria-hidden="true" /> {ru.tablet.back}
      </button>
      <header>
        <p className="auth-brand">{ru.brand}</p>
        <h1>{ru.tablet.title}</h1>
        <p>{ru.tablet.text}</p>
      </header>
      {users.length === 0 && <p className="empty-state">{ru.tablet.noUsers}</p>}
      <div className="avatar-picker">
        {users.map((user) => (
          <button
            type="button"
            className={selected?.id === user.id ? "is-selected" : ""}
            onClick={() => {
              setSelected(user);
              setPin("");
            }}
            key={user.id}
          >
            <span className="avatar tablet-avatar" style={{ background: user.color }}>
              {user.name.slice(0, 1)}
            </span>
            <strong>{user.name}</strong>
          </button>
        ))}
      </div>
      {selected && (
        <form className="pin-form" onSubmit={submit}>
          <label>
            <span>{ru.tablet.pin}</span>
            <input
              autoFocus
              inputMode="numeric"
              type="password"
              pattern="\d{4,6}"
              maxLength={6}
              value={pin}
              onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))}
              required
            />
          </label>
          <button className="primary-button" type="submit">
            {ru.tablet.enter}
          </button>
        </form>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </main>
  );
}

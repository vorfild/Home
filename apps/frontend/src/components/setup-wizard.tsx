import {
  Bell,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  House,
  Upload,
  UserRound,
} from "lucide-react";
import { FormEvent, useState } from "react";

import { api, AuthResponse, jsonBody } from "../lib/api";
import { ru } from "../lib/i18n";

type Props = { onComplete: (auth: AuthResponse) => void };

const steps = [Clock3, UserRound, House, Bell, Upload];

export function SetupWizard({ onComplete }: Props) {
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    language: "ru",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Moscow",
    household_name: "Наш дом",
    admin_name: "",
    admin_login: "",
    admin_password: "",
    admin_color: "#5E7FA3",
    notifications: { in_app: true, web_push: false, email: false },
  });

  function update(name: string, value: string) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (step < steps.length - 1) {
      setStep((current) => current + 1);
      return;
    }
    setBusy(true);
    try {
      const result = await api<AuthResponse>("/setup", { method: "POST", ...jsonBody(form) });
      onComplete(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : ru.common.error);
    } finally {
      setBusy(false);
    }
  }

  const titles = [
    [ru.setup.languageTitle, ru.setup.languageText],
    [ru.setup.adminTitle, ru.setup.adminText],
    [ru.setup.homeTitle, ru.setup.homeText],
    [ru.setup.notificationsTitle, ru.setup.notificationsText],
    [ru.setup.importTitle, ru.setup.importText],
  ];

  return (
    <main className="auth-layout">
      <section className="auth-aside">
        <p className="auth-brand">{ru.brand}</p>
        <div>
          <p className="eyebrow">{ru.setup.eyebrow}</p>
          <h1>{ru.setup.title}</h1>
          <p>{ru.setup.description}</p>
        </div>
        <ol className="setup-progress" aria-label="Этапы настройки">
          {steps.map((StepIcon, index) => (
            <li className={index <= step ? "is-current" : ""} key={index}>
              <span>
                {index < step ? <Check aria-hidden="true" /> : <StepIcon aria-hidden="true" />}
              </span>
              <small>
                {ru.setup.step} {index + 1}
              </small>
            </li>
          ))}
        </ol>
      </section>
      <section className="auth-panel">
        <form className="auth-card setup-card" onSubmit={submit}>
          <div className="step-counter">
            {ru.setup.step} {step + 1} / {steps.length}
          </div>
          <h2>{titles[step][0]}</h2>
          <p className="form-intro">{titles[step][1]}</p>

          {step === 0 && (
            <div className="form-stack">
              <label>
                <span>{ru.setup.language}</span>
                <select value={form.language} disabled>
                  <option value="ru">{ru.setup.russian}</option>
                </select>
              </label>
              <label>
                <span>{ru.setup.timezone}</span>
                <input
                  value={form.timezone}
                  onChange={(event) => update("timezone", event.target.value)}
                  required
                />
              </label>
            </div>
          )}
          {step === 1 && (
            <div className="form-stack">
              <label>
                <span>{ru.setup.name}</span>
                <input
                  autoFocus
                  value={form.admin_name}
                  onChange={(event) => update("admin_name", event.target.value)}
                  required
                  maxLength={100}
                />
              </label>
              <label>
                <span>{ru.setup.login}</span>
                <input
                  value={form.admin_login}
                  onChange={(event) => update("admin_login", event.target.value)}
                  required
                  minLength={3}
                  pattern="[A-Za-z0-9._-]+"
                  autoCapitalize="none"
                />
              </label>
              <label>
                <span>{ru.setup.password}</span>
                <input
                  type="password"
                  value={form.admin_password}
                  onChange={(event) => update("admin_password", event.target.value)}
                  required
                  minLength={12}
                  autoComplete="new-password"
                />
                <small>{ru.setup.passwordHint}</small>
              </label>
            </div>
          )}
          {step === 2 && (
            <label className="house-name-field">
              <span>{ru.setup.homeName}</span>
              <input
                autoFocus
                value={form.household_name}
                onChange={(event) => update("household_name", event.target.value)}
                required
                maxLength={120}
              />
            </label>
          )}
          {step === 3 && (
            <div className="check-stack">
              {(
                [
                  ["in_app", ru.setup.inApp],
                  ["web_push", ru.setup.push],
                  ["email", ru.setup.email],
                ] as const
              ).map(([key, label]) => (
                <label className="check-row" key={key}>
                  <input
                    type="checkbox"
                    checked={form.notifications[key]}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        notifications: { ...current.notifications, [key]: event.target.checked },
                      }))
                    }
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          )}
          {step === 4 && (
            <div className="import-skip">
              <Upload aria-hidden="true" />
              <strong>{ru.setup.importSkip}</strong>
            </div>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="form-actions">
            {step > 0 && (
              <button className="secondary-button" type="button" onClick={() => setStep(step - 1)}>
                <ChevronLeft aria-hidden="true" /> {ru.common.back}
              </button>
            )}
            <button className="primary-button" type="submit" disabled={busy}>
              {step === steps.length - 1 ? ru.common.finish : ru.common.continue}
              <ChevronRight aria-hidden="true" />
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}

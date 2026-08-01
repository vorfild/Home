import { Fragment, useCallback, useEffect, useState } from "react";

import { ChangePasswordScreen, LoginScreen, TabletScreen } from "./components/auth-screens";
import { CalendarPage } from "./components/calendar-page";
import { FamilyPage } from "./components/family-page";
import { HomePage } from "./components/home-page";
import { MobileNavigation, Page, Sidebar } from "./components/navigation";
import { SetupWizard } from "./components/setup-wizard";
import { ShoppingPage } from "./components/shopping-page";
import { SettingsPage } from "./components/settings-page";
import { StoragePage } from "./components/storage-page";
import { TasksPage } from "./components/tasks-page";
import { TodayDashboard } from "./components/today-dashboard";
import {
  api,
  ApiError,
  AuthResponse,
  rememberCsrf,
  SetupStatus,
  TabletStatus,
  User,
  UserPreference,
} from "./lib/api";
import { ru } from "./lib/i18n";
import { useRealtime } from "./lib/realtime";
import { syncShoppingQueue } from "./lib/shopping-offline";
import { syncTaskQueue } from "./lib/task-offline";

type Screen = "loading" | "setup" | "login" | "tablet" | "app";

export function App() {
  const [screen, setScreen] = useState<Screen>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [page, setPage] = useState<Page>(() =>
    window.location.pathname.startsWith("/storage/qr/") ? "storage" : "family",
  );
  const [tabletTrusted, setTabletTrusted] = useState(false);
  const [startupError, setStartupError] = useState("");
  const realtimeRevision = useRealtime(screen === "app" && user !== null);

  const boot = useCallback(async () => {
    setStartupError("");
    setScreen("loading");
    try {
      const setup = await api<SetupStatus>("/setup/status");
      if (setup.setup_required) {
        setScreen("setup");
        return;
      }
      const tablet = await api<TabletStatus>("/tablet/status");
      setTabletTrusted(tablet.trusted);
      try {
        const auth = await api<AuthResponse>("/auth/me");
        rememberCsrf(auth.csrf_token);
        setUser(auth.user);
        setScreen("app");
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 401) {
          setUser(null);
          setScreen(tablet.trusted ? "tablet" : "login");
        } else {
          throw caught;
        }
      }
    } catch (caught) {
      setStartupError(caught instanceof Error ? caught.message : ru.common.error);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(boot);
  }, [boot]);

  useEffect(() => {
    if (screen !== "app" || !user) return;
    void api<UserPreference>("/settings/preferences")
      .then((preference) => {
        document.documentElement.dataset.theme = preference.theme;
        document.documentElement.dataset.fontScale = preference.font_scale;
        document.documentElement.dataset.density = preference.density;
      })
      .catch(() => undefined);
  }, [screen, user]);

  useEffect(() => {
    if (screen !== "app" || !user) return;
    const synchronize = () => {
      void Promise.all([syncTaskQueue(), syncShoppingQueue()]);
    };
    synchronize();
    window.addEventListener("online", synchronize);
    return () => window.removeEventListener("online", synchronize);
  }, [screen, user]);

  function authenticated(auth: AuthResponse) {
    rememberCsrf(auth.csrf_token);
    setUser(auth.user);
    setScreen("app");
  }

  async function logout(next: Screen = "login") {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      /* An expired session is already logged out. */
    }
    rememberCsrf("");
    setUser(null);
    setScreen(next);
  }

  if (startupError)
    return (
      <main className="centered-auth">
        <section className="auth-card login-card">
          <h1>{ru.common.error}</h1>
          <p className="form-error">{startupError}</p>
          <button className="primary-button" type="button" onClick={() => void boot()}>
            {ru.retry}
          </button>
        </section>
      </main>
    );
  if (screen === "loading")
    return (
      <div className="loading-screen">
        <span className="loading-mark">Д</span>
        <p>{ru.loading}</p>
      </div>
    );
  if (screen === "setup") return <SetupWizard onComplete={authenticated} />;
  if (screen === "login")
    return (
      <LoginScreen
        tabletAvailable={tabletTrusted}
        onAuthenticated={authenticated}
        onTablet={() => setScreen("tablet")}
      />
    );
  if (screen === "tablet")
    return <TabletScreen onAuthenticated={authenticated} onBack={() => setScreen("login")} />;
  if (!user) return null;
  if (user.must_change_password) return <ChangePasswordScreen onAuthenticated={authenticated} />;

  return (
    <div className="app-shell">
      <Sidebar active={page} user={user} onNavigate={setPage} onLogout={() => void logout()} />
      <Fragment key={`${page}-${realtimeRevision}`}>
        {page === "family" ? (
          <FamilyPage
            currentUser={user}
            tabletTrusted={tabletTrusted}
            onTabletRegistered={() => setTabletTrusted(true)}
            onEnterTablet={() => void logout("tablet")}
          />
        ) : page === "tasks" ? (
          <TasksPage currentUser={user} />
        ) : page === "shopping" ? (
          <ShoppingPage currentUser={user} />
        ) : page === "storage" ? (
          <StoragePage
            currentUser={user}
            initialQrToken={
              window.location.pathname.startsWith("/storage/qr/")
                ? window.location.pathname.split("/").pop()
                : undefined
            }
          />
        ) : page === "home" ? (
          <HomePage currentUser={user} />
        ) : page === "calendar" ? (
          <CalendarPage
            onToday={() => setPage("today")}
            onOpen={(event) =>
              setPage(
                event.source_type === "task"
                  ? "tasks"
                  : event.source_type === "shopping"
                    ? "shopping"
                    : event.source_type === "storage"
                      ? "storage"
                      : "home",
              )
            }
          />
        ) : page === "settings" ? (
          <SettingsPage currentUser={user} />
        ) : page === "today" ? (
          <TodayDashboard user={user} onOpenShopping={() => setPage("shopping")} />
        ) : (
          <main className="main-content module-page">
            <h1>{ru.nav[page]}</h1>
          </main>
        )}
      </Fragment>
      <MobileNavigation
        active={page}
        user={user}
        onNavigate={setPage}
        onLogout={() => void logout()}
      />
    </div>
  );
}

import {
  CalendarDays,
  ChevronDown,
  ClipboardList,
  House,
  LogOut,
  Menu,
  PackageOpen,
  Settings,
  ShoppingCart,
  Users,
  Warehouse,
} from "lucide-react";

import type { User } from "../lib/api";
import { ru } from "../lib/i18n";

type Icon = typeof House;
export type Page = "today" | "family";

const desktopItems: { label: string; icon: Icon; page?: Page }[] = [
  { label: ru.nav.today, icon: House, page: "today" },
  { label: ru.nav.allTasks, icon: ClipboardList },
  { label: ru.nav.shopping, icon: ShoppingCart },
  { label: ru.nav.storage, icon: Warehouse },
  { label: ru.nav.home, icon: PackageOpen },
  { label: ru.nav.calendar, icon: CalendarDays },
  { label: ru.nav.family, icon: Users, page: "family" },
  { label: ru.nav.settings, icon: Settings },
];

const mobileItems: { label: string; icon: Icon; page?: Page }[] = [
  { label: ru.nav.today, icon: House, page: "today" },
  { label: ru.nav.tasks, icon: ClipboardList },
  { label: ru.nav.shopping, icon: ShoppingCart },
  { label: ru.nav.storage, icon: Warehouse },
  { label: ru.nav.more, icon: Menu, page: "family" },
];

type NavigationProps = {
  active: Page;
  user: User;
  onNavigate: (page: Page) => void;
  onLogout: () => void;
};

function initials(name: string): string {
  return name.trim().slice(0, 1).toUpperCase();
}

export function Sidebar({ active, user, onNavigate, onLogout }: NavigationProps) {
  return (
    <aside className="sidebar" aria-label="Основная навигация">
      <div className="brand">{ru.brand}</div>
      <nav className="nav-list">
        {desktopItems.map(({ label, icon: NavIcon, page }) => (
          <button
            className={`nav-item${page === active ? " is-active" : ""}`}
            type="button"
            key={label}
            disabled={!page}
            onClick={() => page && onNavigate(page)}
          >
            <NavIcon aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="profile-area">
        <button className="profile-switcher" type="button" onClick={() => onNavigate("family")}>
          <span className="avatar" style={{ background: user.color }}>
            {initials(user.name)}
          </span>
          <span>{user.name}</span>
          <ChevronDown aria-hidden="true" />
        </button>
        <button className="logout-button" type="button" onClick={onLogout}>
          <LogOut aria-hidden="true" />
          <span>{ru.auth.logout}</span>
        </button>
      </div>
    </aside>
  );
}

export function MobileNavigation({ active, user, onNavigate, onLogout }: NavigationProps) {
  void user;
  void onLogout;
  return (
    <nav className="mobile-nav" aria-label="Мобильная навигация">
      {mobileItems.map(({ label, icon: NavIcon, page }) => (
        <button
          className={`mobile-nav-item${page === active ? " is-active" : ""}`}
          type="button"
          key={label}
          disabled={!page}
          onClick={() => page && onNavigate(page)}
        >
          <NavIcon aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}

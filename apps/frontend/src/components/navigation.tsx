import {
  CalendarDays,
  ChevronDown,
  ClipboardList,
  House,
  Menu,
  PackageOpen,
  Settings,
  ShoppingCart,
  Users,
  Warehouse,
} from "lucide-react";

import { ru } from "../lib/i18n";

type Icon = typeof House;

const desktopItems: { label: string; icon: Icon; active?: boolean }[] = [
  { label: ru.today, icon: House, active: true },
  { label: ru.allTasks, icon: ClipboardList },
  { label: ru.shopping, icon: ShoppingCart },
  { label: ru.storage, icon: Warehouse },
  { label: ru.home, icon: PackageOpen },
  { label: ru.calendar, icon: CalendarDays },
  { label: ru.family, icon: Users },
  { label: ru.settings, icon: Settings },
];

const mobileItems: { label: string; icon: Icon; active?: boolean }[] = [
  { label: ru.today, icon: House, active: true },
  { label: "Дела", icon: ClipboardList },
  { label: ru.shopping, icon: ShoppingCart },
  { label: ru.storage, icon: Warehouse },
  { label: ru.more, icon: Menu },
];

export function Sidebar() {
  return (
    <aside className="sidebar" aria-label="Основная навигация">
      <div className="brand">{ru.brand}</div>
      <nav className="nav-list">
        {desktopItems.map(({ label, icon: NavIcon, active }) => (
          <button className={`nav-item${active ? " is-active" : ""}`} type="button" key={label}>
            <NavIcon aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <button className="profile-switcher" type="button" aria-label="Меню пользователя Алексей">
        <span className="avatar avatar-blue">А</span>
        <span>Алексей</span>
        <ChevronDown aria-hidden="true" />
      </button>
    </aside>
  );
}

export function MobileNavigation() {
  return (
    <nav className="mobile-nav" aria-label="Мобильная навигация">
      {mobileItems.map(({ label, icon: NavIcon, active }) => (
        <button
          className={`mobile-nav-item${active ? " is-active" : ""}`}
          type="button"
          key={label}
        >
          <NavIcon aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}

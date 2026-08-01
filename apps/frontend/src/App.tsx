import { MobileNavigation, Sidebar } from "./components/navigation";
import { TodayDashboard } from "./components/today-dashboard";

export function App() {
  return (
    <div className="app-shell">
      <Sidebar />
      <TodayDashboard />
      <MobileNavigation />
    </div>
  );
}

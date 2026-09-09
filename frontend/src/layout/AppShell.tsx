import { Button } from "@heroui/react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { logout } from "../api";

const links = [
  { to: "/camera", label: "الكاميرا" },
  { to: "/classes", label: "الصفوف" },
  { to: "/students", label: "الطلاب" },
  { to: "/attendance", label: "الحضور" },
];

export function AppShell({ children, onLoggedOut }: { children: ReactNode; onLoggedOut: () => void }) {
  const location = useLocation();
  const [leaving, setLeaving] = useState(false);

  async function onLogout() {
    setLeaving(true);
    try {
      await logout();
      onLoggedOut();
    } finally {
      setLeaving(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-6 sm:px-6">
      <header className="mb-6 flex flex-col gap-4 rounded-3xl border border-border/70 bg-surface/90 p-4 shadow-sm backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <NavLink to="/camera" className="flex items-center gap-3">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-accent text-lg font-extrabold text-accent-foreground">
            س
          </span>
          <span>
            <span className="block text-xl font-extrabold">سهل</span>
            <span className="block text-sm text-muted">إدارة حضور المدرسة</span>
          </span>
        </NavLink>
        <nav className="flex flex-wrap items-center gap-2">
          {links.map((link) => {
            const active = location.pathname === link.to || location.pathname.startsWith(`${link.to}/`);
            return (
              <Button
                key={link.to}
                size="sm"
                variant={active ? "primary" : "ghost"}
                render={(props) => <NavLink {...props} to={link.to} />}
              >
                {link.label}
              </Button>
            );
          })}
          <Button size="sm" variant="ghost" isPending={leaving} onPress={onLogout}>
            خروج
          </Button>
        </nav>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}

export function useUnauthorizedListener(onUnauthorized: () => void) {
  useEffect(() => {
    const handler = () => onUnauthorized();
    window.addEventListener("sahal:unauthorized", handler);
    return () => window.removeEventListener("sahal:unauthorized", handler);
  }, [onUnauthorized]);
}

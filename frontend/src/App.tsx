import { Navigate, Route, Routes } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import { sessionStatus } from "./api";
import { AppShell, useUnauthorizedListener } from "./layout/AppShell";
import { AttendancePage } from "./pages/AttendancePage";
import { CameraPage } from "./pages/CameraPage";
import { ClassroomPage } from "./pages/ClassroomPage";
import { ClassesPage } from "./pages/ClassesPage";
import { LoginPage } from "./pages/LoginPage";
import { StudentsPage } from "./pages/StudentsPage";

export default function App() {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setAuthed(await sessionStatus());
    } catch {
      setAuthed(false);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onLoggedOut = useCallback(() => setAuthed(false), []);
  useUnauthorizedListener(onLoggedOut);

  if (!ready) {
    return <p className="p-8 text-muted">جاري فتح سهل...</p>;
  }

  if (!authed) {
    return <LoginPage onLoggedIn={() => setAuthed(true)} />;
  }

  return (
    <AppShell onLoggedOut={onLoggedOut}>
      <Routes>
        <Route path="/" element={<Navigate to="/camera" replace />} />
        <Route path="/login" element={<Navigate to="/camera" replace />} />
        <Route path="/camera" element={<CameraPage />} />
        <Route path="/classes" element={<ClassesPage />} />
        <Route path="/classes/:id" element={<ClassroomPage />} />
        <Route path="/students" element={<StudentsPage />} />
        <Route path="/attendance" element={<AttendancePage />} />
      </Routes>
    </AppShell>
  );
}

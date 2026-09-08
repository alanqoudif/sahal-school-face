import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { AttendancePage } from "./pages/AttendancePage";
import { CameraPage } from "./pages/CameraPage";
import { ClassroomPage } from "./pages/ClassroomPage";
import { ClassesPage } from "./pages/ClassesPage";
import { StudentsPage } from "./pages/StudentsPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/camera" replace />} />
        <Route path="/camera" element={<CameraPage />} />
        <Route path="/classes" element={<ClassesPage />} />
        <Route path="/classes/:id" element={<ClassroomPage />} />
        <Route path="/students" element={<StudentsPage />} />
        <Route path="/attendance" element={<AttendancePage />} />
      </Routes>
    </AppShell>
  );
}

import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import Chat from "./pages/Chat";
import TicketReview from "./pages/TicketReview";
import Runs from "./pages/Runs";
import SettingsPage from "./pages/Settings";

export default function App() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>AI Consultant</h1>
        <nav>
          <NavLink to="/projects" className={({ isActive }) => (isActive ? "active" : "")}>
            Projects
          </NavLink>
          <NavLink to="/tickets" className={({ isActive }) => (isActive ? "active" : "")}>
            Ticket Review
          </NavLink>
          <NavLink to="/runs" className={({ isActive }) => (isActive ? "active" : "")}>
            Runs
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => (isActive ? "active" : "")}>
            Settings
          </NavLink>
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/projects" replace />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:id" element={<ProjectDetail />} />
          <Route path="/projects/:id/chat/:sessionId?" element={<Chat />} />
          <Route path="/tickets" element={<TicketReview />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}

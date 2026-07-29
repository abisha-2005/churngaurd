import { useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./components/Sidebar.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Upload from "./pages/Upload.jsx";
import Results from "./pages/Results.jsx";
import SmsLogs from "./pages/SmsLogs.jsx";
import { api } from "./api.js";

export default function App() {
  const [user, setUser] = useState(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("churnguard_token");
    if (!token) {
      setChecked(true);
      return;
    }
    api.me().then(setUser).catch(() => {}).finally(() => setChecked(true));
  }, []);

  if (!checked) return null;

  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<Login onAuth={setUser} />} />
      </Routes>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar user={user} />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/results/:id" element={<Results />} />
        <Route path="/sms-logs" element={<SmsLogs />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </div>
  );
}

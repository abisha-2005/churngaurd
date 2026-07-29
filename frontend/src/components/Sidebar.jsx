import { Link, useLocation, useNavigate } from "react-router-dom";
import { clearToken } from "../api.js";

export default function Sidebar({ user }) {
  const location = useLocation();
  const navigate = useNavigate();

  const links = [
    { to: "/dashboard", label: "Dashboard", icon: "▦" },
    { to: "/upload", label: "Upload CSV", icon: "⬆" },
    { to: "/sms-logs", label: "SMS Logs", icon: "💬" },
  ];

  function handleSignOut() {
    clearToken();
    navigate("/login");
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">📉</div>
        ChurnGuard
      </div>

      <nav className="sidebar-nav">
        {links.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className={`sidebar-link ${location.pathname.startsWith(link.to) ? "active" : ""}`}
          >
            <span>{link.icon}</span>
            {link.label}
          </Link>
        ))}
      </nav>

      {user && (
        <div className="sidebar-user">
          <div className="sidebar-user-avatar">{user.business_name?.[0]?.toUpperCase() || "?"}</div>
          <div>
            <div className="sidebar-user-name">{user.business_name}</div>
            <div className="sidebar-user-email">{user.email}</div>
          </div>
        </div>
      )}
      <div className="sign-out" onClick={handleSignOut}>⏻ Sign Out</div>
    </aside>
  );
}

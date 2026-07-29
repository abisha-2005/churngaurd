import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../api.js";

export default function Login({ onAuth }) {
  const [mode, setMode] = useState("signup"); // "signin" | "signup"
  const [form, setForm] = useState({
    business_name: "", website: "", phone: "", email: "", password: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const payload =
        mode === "signup"
          ? form
          : { email: form.email, password: form.password };

      const res = mode === "signup" ? await api.signup(payload) : await api.login(payload);
      setToken(res.access_token);
      const me = await api.me();
      onAuth(me);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-left">
        <h1>
          Stop customers from<br />
          <span className="highlight">leaving before they go.</span>
        </h1>
        <p style={{ color: "var(--text-dim)", fontSize: 18, maxWidth: 480, marginBottom: 40 }}>
          Upload your customer data and get an AI-powered churn analysis with retention
          recommendations in minutes.
        </p>

        <div className="feature-row">
          <div className="feature-icon">📊</div>
          <div>
            <h3>AI Churn Prediction</h3>
            <p>XGBoost + Random Forest ensemble</p>
          </div>
        </div>
        <div className="feature-row">
          <div className="feature-icon">⚡</div>
          <div>
            <h3>Instant Analysis</h3>
            <p>Results in under 30 seconds</p>
          </div>
        </div>
        <div className="feature-row">
          <div className="feature-icon">🛡️</div>
          <div>
            <h3>SMS &amp; Email Retention</h3>
            <p>Reach at-risk customers instantly</p>
          </div>
        </div>
      </div>

      <div className="auth-right">
        <div className="auth-toggle">
          <button className={mode === "signin" ? "active" : ""} onClick={() => setMode("signin")}>
            Sign In
          </button>
          <button className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>
            Create Account
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {mode === "signup" && (
            <>
              <div className="field">
                <label>Business Name</label>
                <input className="input" required value={form.business_name}
                  onChange={(e) => update("business_name", e.target.value)} />
              </div>
              <div className="grid cols-2">
                <div className="field">
                  <label>Website</label>
                  <input className="input" value={form.website}
                    onChange={(e) => update("website", e.target.value)} />
                </div>
                <div className="field">
                  <label>Phone</label>
                  <input className="input" value={form.phone}
                    onChange={(e) => update("phone", e.target.value)} />
                </div>
              </div>
            </>
          )}

          <div className="field">
            <label>Email Address</label>
            <input className="input" type="email" required value={form.email}
              onChange={(e) => update("email", e.target.value)} />
          </div>
          <div className="field">
            <label>Password</label>
            <input className="input" type="password" required value={form.password}
              onChange={(e) => update("password", e.target.value)} />
          </div>

          {error && <div className="error-text">{error}</div>}

          <button className="btn" type="submit" disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
            {loading ? "Please wait..." : mode === "signup" ? "Create Account" : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}

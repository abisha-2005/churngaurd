import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../api.js";

const RISK_COLORS = { "High Risk": "#f4527a", "Medium Risk": "#f5a623", "Low Risk": "#2ecc9b" };
const SEGMENT_COLORS = ["#6c5ce7", "#2ecc9b", "#f5a623", "#f4527a", "#3fb6ff"];

function riskClass(level) {
  if (level === "High Risk") return "high";
  if (level === "Medium Risk") return "medium";
  return "low";
}

// Escapes HTML first (safety, since this becomes innerHTML), then converts
// **bold** markdown (common in Gemini/Ollama answers) into <strong> tags.
function renderChatText(text) {
  const escaped = String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  const withBold = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  return { __html: withBold };
}

export default function Results() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState("All Risk");
  const [verifiedNumber, setVerifiedNumber] = useState("");
  const [sending, setSending] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [question, setQuestion] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [advisorUseLocal, setAdvisorUseLocal] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [campaignStatus, setCampaignStatus] = useState("");

  async function load() {
    try {
      const res = await api.results(id);
      setData(res);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    api.advisorHistory(id).then(setChatHistory).catch(() => {});
  }, [id]);

  async function handleSendAlert(customerId) {
    setSending(customerId);
    try {
      const res = await api.sendAlert(id, customerId, verifiedNumber || undefined);
      const statuses = Object.entries(res.results)
        .map(([channel, r]) => `${channel.toUpperCase()}: ${r.status}`)
        .join(" | ");
      alert(`Sent to ${customerId} — ${statuses}`);
    } catch (err) {
      alert(err.message);
    } finally {
      setSending(null);
    }
  }

  async function handleCampaign() {
    setCampaignStatus("Sending...");
    try {
      const res = await api.sendCampaign(id, verifiedNumber || undefined);
      setCampaignStatus(`Sent to ${res.sent_count} customers (${res.skipped_count} skipped — no contact info)`);
    } catch (err) {
      setCampaignStatus(err.message);
    }
  }

  async function handleAsk(e) {
    e.preventDefault();
    if (!question.trim()) return;
    setChatLoading(true);
    const q = question;
    setQuestion("");
    setChatHistory((h) => [...h, { role: "user", content: q }]);
    try {
      const res = await api.advisorChat(id, q, advisorUseLocal);
      setChatHistory((h) => [...h, { role: "assistant", content: res.answer, backend: res.backend }]);
    } catch (err) {
      setChatHistory((h) => [...h, { role: "assistant", content: `Error: ${err.message}` }]);
    } finally {
      setChatLoading(false);
    }
  }

  async function handleDownloadReport() {
    setReportLoading(true);
    try {
      const res = await fetch(api.reportUrl(id), {
        headers: { Authorization: `Bearer ${localStorage.getItem("churnguard_token")}` },
      });
      if (!res.ok) throw new Error("Could not generate report");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "retention_report.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err.message);
    } finally {
      setReportLoading(false);
    }
  }

  if (error) return <div className="main-content"><p className="error-text">{error}</p></div>;
  if (!data) return <div className="main-content"><p className="loading-text">Loading results...</p></div>;

  const riskData = Object.entries(data.risk_distribution || {}).map(([name, value]) => ({ name, value }));
  const segmentData = Object.entries(data.segment_distribution || {}).map(([name, value]) => ({ name, value }));
  const revenueData = Object.entries(data.revenue_by_risk || {}).map(([name, value]) => ({ name, value }));

  const filteredCustomers = (data.customers || []).filter((c) => {
    const matchesSearch = !search || String(c.customer_id).toLowerCase().includes(search.toLowerCase());
    const matchesRisk = riskFilter === "All Risk" || c.risk_level === riskFilter;
    return matchesSearch && matchesRisk;
  });

  const comparison = data.model_comparison || {};
  const modelKeys = Object.keys(comparison).filter((k) => k !== "best");

  return (
    <div className="main-content">
      <div className="breadcrumb">
        <Link to="/dashboard">Dashboard</Link> &nbsp;›&nbsp; {data.analysis.filename}
      </div>
      <div className="page-header">
        <h1>Analysis Results</h1>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="btn secondary" onClick={load}>↻ Refresh</button>
          <button className="btn" onClick={handleCampaign}>➤ SMS Campaign</button>
        </div>
      </div>
      {campaignStatus && <p className="loading-text" style={{ marginTop: -16, marginBottom: 20 }}>{campaignStatus}</p>}

      <div className="grid cols-4" style={{ marginBottom: 24 }}>
        <div className="card stat-card">
          <span className="label">Total Customers</span>
          <span className="value">{data.total_customers}</span>
          <span className="sub">records analyzed</span>
        </div>
        <div className="card stat-card danger">
          <span className="label">Churn Rate</span>
          <span className="value">{data.churn_rate}%</span>
          <span className="sub">predicted churners</span>
        </div>
        <div className="card stat-card warning">
          <span className="label">High Risk</span>
          <span className="value">{data.risk_distribution?.["High Risk"] || 0}</span>
          <span className="sub">need immediate action</span>
        </div>
        <div className="card stat-card success">
          <span className="label">Model Accuracy</span>
          <span className="value">{data.model_metrics ? (data.model_metrics.accuracy * 100).toFixed(2) : "—"}%</span>
          <span className="sub">{comparison.best ? comparison[comparison.best]?.label : ""}</span>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginBottom: 24 }}>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Risk Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={riskData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90}>
                {riskData.map((entry, i) => <Cell key={i} fill={RISK_COLORS[entry.name] || "#6c5ce7"} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
            {riskData.map((r) => (
              <div key={r.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
                <span><span style={{ color: RISK_COLORS[r.name] }}>●</span> {r.name}</span>
                <b>{r.value}</b>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Churn by Segment</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={segmentData}>
              <XAxis dataKey="name" stroke="#9494a8" fontSize={12} />
              <YAxis stroke="#9494a8" fontSize={12} />
              <Tooltip />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {segmentData.map((_, i) => <Cell key={i} fill={SEGMENT_COLORS[i % SEGMENT_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginBottom: 24 }}>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Top Churn Drivers</h3>
          {(data.top_drivers || []).map((d) => (
            <div className="driver-row" key={d.feature}>
              <div className="driver-row-top"><span>{d.feature}</span><b>{d.importance_pct}%</b></div>
              <div className="driver-bar"><div className="driver-bar-fill" style={{ width: `${d.importance_pct}%` }} /></div>
            </div>
          ))}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Model Comparison</h3>
          {modelKeys.map((key) => {
            const m = comparison[key];
            return (
              <div className="model-card" key={key}>
                <div className="model-card-header">
                  <b>{m.label}</b>
                  {comparison.best === key && <span className="best-badge">Best</span>}
                </div>
                <div className="model-card-metrics">
                  <div><span className="metric-value">{m.accuracy}%</span><span className="metric-label">Acc</span></div>
                  <div><span className="metric-value">{m.precision}%</span><span className="metric-label">Prec</span></div>
                  <div><span className="metric-value">{m.recall}%</span><span className="metric-label">Recall</span></div>
                  <div><span className="metric-value">{m.auc ?? "N/A"}{m.auc != null ? "%" : ""}</span><span className="metric-label">AUC</span></div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>Customer Records ({filteredCustomers.length})</h3>
          <div style={{ display: "flex", gap: 10 }}>
            <input className="input" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 200 }} />
            <select className="input" value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)} style={{ width: 160 }}>
              <option>All Risk</option>
              <option>High Risk</option>
              <option>Medium Risk</option>
              <option>Low Risk</option>
            </select>
          </div>
        </div>

        <div className="field" style={{ maxWidth: 360 }}>
          <label>Twilio-verified test number (trial mode only sends here)</label>
          <input className="input" placeholder="+91XXXXXXXXXX" value={verifiedNumber} onChange={(e) => setVerifiedNumber(e.target.value)} />
        </div>

        <table>
          <thead>
            <tr>
              <th>Customer</th><th>Segment</th><th>Risk</th><th>Churn %</th><th>Reason</th><th>SMS</th>
            </tr>
          </thead>
          <tbody>
            {filteredCustomers.slice(0, 50).map((c) => (
              <tr key={c.customer_id}>
                <td>{c.customer_id}</td>
                <td>{c.segment}</td>
                <td><span className={`badge ${riskClass(c.risk_level)}`}>{c.risk_level}</span></td>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div className="progress-bar"><div className="progress-bar-fill" style={{ width: `${(c.churn_probability * 100).toFixed(0)}%` }} /></div>
                    {(c.churn_probability * 100).toFixed(1)}%
                  </div>
                </td>
                <td style={{ maxWidth: 260, fontSize: 13, color: "var(--text-dim)" }}>{c.risk_reason || "—"}</td>
                <td>
                  <button className="btn secondary" disabled={sending === c.customer_id}
                    onClick={() => handleSendAlert(c.customer_id)}>
                    {sending === c.customer_id ? "..." : "📩 Send"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginTop: 0 }}>💬 AI Strategy Advisor</h3>
        <p style={{ color: "var(--text-dim)", fontSize: 14 }}>
          Ask things like "who should I target with offers?" or "how much revenue is at risk?"
        </p>
        <label style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-dim)", fontSize: 14, marginBottom: 14 }}>
          <input type="checkbox" checked={advisorUseLocal} onChange={(e) => setAdvisorUseLocal(e.target.checked)} />
          Force local Ollama model (skip Gemini)
        </label>

        <div className="chat-window">
          {chatHistory.length === 0 && <p className="loading-text">No questions yet — ask one below.</p>}
          {chatHistory.map((m, i) => (
            <div key={i} className={`chat-bubble ${m.role}`}>
              <span dangerouslySetInnerHTML={renderChatText(m.content)} />
              {m.backend && (
                <div className="chat-backend-label">
                  {m.backend === "gemini" ? "🟢 Gemini" : m.backend === "ollama" ? "🟡 Local Ollama" : "⚪ Offline fallback"}
                </div>
              )}
            </div>
          ))}
        </div>

        <form className="chat-input-row" onSubmit={handleAsk}>
          <input className="input" placeholder="e.g. who should I target with offers?"
            value={question} onChange={(e) => setQuestion(e.target.value)} />
          <button className="btn" type="submit" disabled={chatLoading}>{chatLoading ? "Thinking..." : "Ask"}</button>
        </form>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>📊 Downloadable Report</h3>
        <p style={{ color: "var(--text-dim)", fontSize: 14 }}>
          Download a full PDF report with charts, model metrics, the high-risk customer table
          with reasons, and the notification log.
        </p>
        <button className="btn" disabled={reportLoading} onClick={handleDownloadReport}>
          {reportLoading ? "Building PDF..." : "⬇ Download Retention Report (PDF)"}
        </button>
      </div>
    </div>
  );
}
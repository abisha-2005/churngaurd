import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

const STATUS_LABEL = {
  uploaded: "Awaiting mapping",
  mapped: "Ready to train",
  trained: "Trained",
  explained: "Complete",
};

export default function Dashboard() {
  const [analyses, setAnalyses] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api.listAnalyses().then(setAnalyses).finally(() => setLoading(false));
  }, []);

  return (
    <div className="main-content">
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p>Your churn analysis history</p>
        </div>
        <button className="btn" onClick={() => navigate("/upload")}>⬆ New Analysis</button>
      </div>

      {loading ? (
        <p className="loading-text">Loading...</p>
      ) : analyses.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">📊</div>
            <h2 style={{ margin: "0 0 8px 0" }}>No analyses yet</h2>
            <p style={{ color: "var(--text-dim)", marginBottom: 24 }}>
              Upload your first customer CSV to get started
            </p>
            <button className="btn" onClick={() => navigate("/upload")}>⬆ Upload CSV</button>
          </div>
        </div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Status</th>
                <th>Customers</th>
                <th>Churn Rate</th>
                <th>High Risk</th>
                <th>Model Accuracy</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {analyses.map((a) => (
                <tr key={a.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/results/${a.id}`)}>
                  <td>{a.filename}</td>
                  <td>{STATUS_LABEL[a.status] || a.status}</td>
                  <td>{a.total_customers ?? "—"}</td>
                  <td>{a.churn_rate != null ? `${a.churn_rate}%` : "—"}</td>
                  <td>{a.high_risk_count ?? "—"}</td>
                  <td>{a.model_accuracy != null ? `${a.model_accuracy.toFixed(1)}%` : "—"}</td>
                  <td>
                    <button className="btn secondary" onClick={(e) => { e.stopPropagation(); navigate(`/results/${a.id}`); }}>
                      View →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

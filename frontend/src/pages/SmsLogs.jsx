import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";

export default function SmsLogs() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [analysisId, setAnalysisId] = useState("");
  const [params] = useSearchParams();

  useEffect(() => {
    const id = params.get("analysis_id");
    if (id) setAnalysisId(id);
  }, [params]);

  async function load(id) {
    if (!id) return;
    setLoading(true);
    try {
      const res = await api.notifications(id);
      setLogs(res);
    } catch (_) {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { if (analysisId) load(analysisId); }, [analysisId]);

  return (
    <div className="main-content">
      <div className="page-header">
        <div>
          <h1>SMS Logs</h1>
          <p>Notification history for sent alerts</p>
        </div>
      </div>

      <div className="field" style={{ maxWidth: 320 }}>
        <label>Analysis ID</label>
        <input className="input" placeholder="e.g. 3" value={analysisId}
          onChange={(e) => setAnalysisId(e.target.value)}
          onBlur={() => load(analysisId)} />
      </div>

      <div className="card">
        {loading ? (
          <p className="loading-text">Loading...</p>
        ) : !analysisId ? (
          <p className="loading-text">Enter an Analysis ID above to view its notification history.</p>
        ) : logs.length === 0 ? (
          <p className="loading-text">No notifications sent yet.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Customer</th><th>Channel</th><th>Status</th><th>Sent At</th></tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id}>
                  <td>{l.customer_id}</td>
                  <td>{l.channel}</td>
                  <td>{l.status}</td>
                  <td>{l.sent_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
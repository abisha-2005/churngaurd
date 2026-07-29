import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

const EXPECTED_COLS = [
  "CustomerID", "Gender", "SeniorCitizen", "Partner", "Dependents", "tenure",
  "PhoneService", "InternetService", "Contract", "MonthlyCharges", "TotalCharges", "Churn",
];

export default function Upload() {
  const [file, setFile] = useState(null);
  const [analysisId, setAnalysisId] = useState(null);
  const [columnInfo, setColumnInfo] = useState(null);
  const [mapping, setMapping] = useState(null);
  const [standardFields, setStandardFields] = useState([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [useLocal, setUseLocal] = useState(false);
  const [step, setStep] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // --- Predict-only mode state ---
  const [mode, setMode] = useState("train"); // "train" | "predict"
  const [trainedAnalyses, setTrainedAnalyses] = useState([]);
  const [sourceAnalysisId, setSourceAnalysisId] = useState("");

  const inputRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    // Load past analyses so the user can pick one with a trained model
    api.listAnalyses()
      .then((list) => setTrainedAnalyses(list.filter((a) => a.status === "trained" || a.status === "explained")))
      .catch(() => {});
  }, []);

  function handleFile(f) {
    if (f && f.name.endsWith(".csv")) {
      setFile(f);
      setError("");
    }
  }

  async function runFullPipeline() {
    if (mode === "predict" && !sourceAnalysisId) {
      setError("Please select an existing trained model to use for prediction.");
      return;
    }

    setError("");
    setLoading(true);
    try {
      setStep("Uploading CSV...");
      const uploadRes = await api.upload(file);
      setAnalysisId(uploadRes.analysis_id);
      setColumnInfo(uploadRes.column_info);

      setStep("AI detecting column meaning...");
      const mapRes = await api.detectMapping(uploadRes.analysis_id, useLocal);
      setStandardFields(mapRes.standard_fields);

      if (showAdvanced) {
        setMapping(mapRes.mapping);
        setLoading(false);
        setStep("");
        return;
      }

      await proceedWithMapping(uploadRes.analysis_id, mapRes.mapping);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  async function proceedWithMapping(id, finalMapping) {
    setLoading(true);
    try {
      setStep("Engineering RFM features & segments...");
      await api.confirmMapping(id, finalMapping);

      if (mode === "predict") {
        setStep("Predicting churn risk using existing model...");
        await api.predict(id, Number(sourceAnalysisId));
        navigate(`/results/${id}`);
        return;
      }

      setStep("Training churn prediction models...");
      await api.train(id);

      setStep("Generating explainable AI risk reasons...");
      await api.explain(id);

      navigate(`/results/${id}`);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  return (
    <div className="main-content">
      <div className="page-header">
        <div>
          <h1>Upload CSV</h1>
          <p>Upload a CSV with customer records. AI will predict churn risk and segment customers automatically.</p>
        </div>
      </div>

      {!mapping && (
        <>
          <div className="card" style={{ marginBottom: 20 }}>
            <h3 style={{ marginTop: 0 }}>What do you want to do?</h3>
            <div style={{ display: "flex", gap: 16 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input type="radio" name="mode" checked={mode === "train"} onChange={() => setMode("train")} />
                Train a new model (dataset has a churn column)
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input type="radio" name="mode" checked={mode === "predict"} onChange={() => setMode("predict")} />
                Predict using an existing model (no churn column needed)
              </label>
            </div>

            {mode === "predict" && (
              <div className="field" style={{ marginTop: 16 }}>
                <label>Select a previously trained analysis</label>
                <select className="input" value={sourceAnalysisId}
                  onChange={(e) => setSourceAnalysisId(e.target.value)}>
                  <option value="">— Choose a trained model —</option>
                  {trainedAnalyses.map((a) => (
                    <option key={a.id} value={a.id}>
                      #{a.id} — {a.filename}
                    </option>
                  ))}
                </select>
                {trainedAnalyses.length === 0 && (
                  <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 6 }}>
                    No trained models found yet. Train one first using a dataset that has a churn column.
                  </p>
                )}
              </div>
            )}
          </div>

          <div
            className="upload-zone"
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); handleFile(e.dataTransfer.files[0]); }}
          >
            <input ref={inputRef} type="file" accept=".csv" hidden
              onChange={(e) => handleFile(e.target.files[0])} />
            {file ? (
              <>
                <div className="upload-zone-icon">📄</div>
                <h2 style={{ margin: "0 0 4px 0" }}>{file.name}</h2>
                <p style={{ color: "var(--text-dim)" }}>{(file.size / 1024).toFixed(1)} KB</p>
                <p className="sign-out" style={{ display: "inline-block" }}
                  onClick={(e) => { e.stopPropagation(); setFile(null); }}>Remove file</p>
              </>
            ) : (
              <>
                <div className="upload-zone-icon">⬆</div>
                <h2 style={{ margin: "0 0 4px 0" }}>Drop your CSV here</h2>
                <p style={{ color: "var(--text-dim)" }}>or click to browse — max 50MB</p>
              </>
            )}
          </div>

          <div style={{ margin: "20px 0" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-dim)", fontSize: 14 }}>
              <input type="checkbox" checked={useLocal} onChange={(e) => setUseLocal(e.target.checked)} />
              Use local Ollama model instead of Gemini for column detection
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-dim)", fontSize: 14, marginTop: 8 }}>
              <input type="checkbox" checked={showAdvanced} onChange={(e) => setShowAdvanced(e.target.checked)} />
              Review &amp; override AI column mapping before analyzing
            </label>
          </div>

          <button className="btn" disabled={!file || loading} onClick={runFullPipeline} style={{ width: "100%", justifyContent: "center", padding: 16 }}>
            {loading ? step || "Working..." : mode === "predict" ? "Predict Churn Risk" : "Start Analysis"}
          </button>

          {error && <div className="error-text">{error}</div>}

          {mode === "train" && (
            <div className="card" style={{ marginTop: 24 }}>
              <h3 style={{ margin: "0 0 6px 0" }}>📋 Expected CSV Columns</h3>
              <p style={{ color: "var(--text-dim)", fontSize: 14, marginBottom: 16 }}>
                Works best with the Kaggle Telco Churn dataset format — but any customer dataset
                works, AI maps your columns automatically.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {EXPECTED_COLS.map((c) => (
                  <span key={c} className="badge low" style={{ background: "var(--panel-2)", color: "var(--text-dim)" }}>{c}</span>
                ))}
              </div>
              <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 12 }}>
                Optional: <b>Name, Email, Phone</b> columns enable SMS &amp; email retention features.
              </p>
            </div>
          )}
        </>
      )}

      {mapping && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Review AI Column Mapping</h3>
          <p style={{ color: "var(--text-dim)", fontSize: 14 }}>Override any wrong guess before continuing.</p>

          {Object.entries(mapping).map(([col, guess]) => (
            <div className="field" key={col}>
              <label>{col}</label>
              <select className="input" value={guess}
                onChange={(e) => setMapping((m) => ({ ...m, [col]: e.target.value }))}>
                {standardFields.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
          ))}

          {error && <div className="error-text">{error}</div>}

          <button className="btn" disabled={loading} onClick={() => proceedWithMapping(analysisId, mapping)} style={{ width: "100%", justifyContent: "center", marginTop: 8 }}>
            {loading ? step || "Working..." : "✅ Confirm Mapping & Continue"}
          </button>
        </div>
      )}
    </div>
  );
}
const BASE_URL = "/api";

function getToken() {
  return localStorage.getItem("churnguard_token");
}

export function setToken(token) {
  localStorage.setItem("churnguard_token", token);
}

export function clearToken() {
  localStorage.removeItem("churnguard_token");
}

async function request(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!isForm && body) headers["Content-Type"] = "application/json";

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  return res;
}

export const api = {
  signup: (payload) => request("/auth/signup", { method: "POST", body: payload }),
  login: (payload) => request("/auth/login", { method: "POST", body: payload }),
  me: () => request("/auth/me"),

  listAnalyses: () => request("/analyses"),
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/analyses/upload", { method: "POST", body: form, isForm: true });
  },
  detectMapping: (id, use_local) =>
    request(`/analyses/${id}/detect-mapping`, { method: "POST", body: { use_local } }),
  confirmMapping: (id, mapping) =>
    request(`/analyses/${id}/confirm-mapping`, { method: "POST", body: { mapping } }),
  train: (id) => request(`/analyses/${id}/train`, { method: "POST" }),
  predict: (id, source_analysis_id) =>
    request(`/analyses/${id}/predict`, { method: "POST", body: { source_analysis_id } }),
    explain: (id) => request(`/analyses/${id}/explain`, { method: "POST" }),
  results: (id) => request(`/analyses/${id}/results`),

  sendAlert: (id, customerId, verified_test_number) =>
    request(`/analyses/${id}/alert/${customerId}`, { method: "POST", body: { verified_test_number } }),
  sendCampaign: (id, verified_test_number) =>
    request(`/analyses/${id}/alerts/campaign`, { method: "POST", body: { verified_test_number } }),
  notifications: (id) => request(`/analyses/${id}/notifications`),

  advisorChat: (id, question, use_local) =>
    request(`/analyses/${id}/advisor/chat`, { method: "POST", body: { question, use_local } }),
  advisorHistory: (id) => request(`/analyses/${id}/advisor/history`),

  reportUrl: (id) => `${BASE_URL}/analyses/${id}/report`,
};

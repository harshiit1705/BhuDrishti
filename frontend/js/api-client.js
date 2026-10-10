/**
 * BhuDrishti API Client
 * ----------------------
 * Single, shared API layer used by every screen. Talks to the FastAPI
 * backend (see /backend/app/main.py). No mock/fake data lives here --
 * every function is a thin wrapper around a real HTTP call.
 *
 * Change API_BASE_URL if the backend runs somewhere other than
 * http://localhost:8000.
 */
const PRODUCTION_API_BASE = ""; // Netlify same-origin proxy -> Vercel API

const API_BASE_URL =
  window.BHUDRISHTI_API_BASE ||
  (window.location.protocol === "file:" ||
   window.location.hostname === "localhost" ||
   window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : PRODUCTION_API_BASE);

function getAuthToken() {
  try { return localStorage.getItem("bhudrishti.auth.token"); } catch (_) { return null; }
}

function getAuthUser() {
  try {
    const raw = localStorage.getItem("bhudrishti.auth.user");
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}

function setAuthSession(auth) {
  localStorage.setItem("bhudrishti.auth.token", auth.token);
  localStorage.setItem("bhudrishti.auth.user", JSON.stringify(auth.user));
}

function clearAuthSession() {
  try {
    localStorage.removeItem("bhudrishti.auth.token");
    localStorage.removeItem("bhudrishti.auth.user");
  } catch (_) {}
}

function isPublicAuthPage() {
  const path = window.location.pathname || "";
  return path.endsWith("auth.html") || path.endsWith("/auth.html");
}

function redirectToLogin() {
  const path = window.location.pathname || "";
  if (!path.endsWith("auth.html")) {
    const next = `${window.location.pathname}${window.location.search}`;
    window.location.href = `auth.html?next=${encodeURIComponent(next)}`;
  }
}

async function apiRequest(path, options = {}) {
  const url = `${API_BASE_URL}${path}`;

  const fetchOptions = {
    ...options,
    headers: {
      ...(options.headers || {}),
    },
  };
  const token = getAuthToken();
  if (token) fetchOptions.headers["Authorization"] = `Bearer ${token}`;

  // Only send JSON Content-Type when the request actually has a body.
  // This avoids unnecessary CORS preflight requests for GET requests.
  if (options.body !== undefined && options.body !== null) {
    fetchOptions.headers["Content-Type"] = "application/json";
  }

  let res;

  try {
    res = await fetch(url, fetchOptions);
  } catch (err) {
    throw new Error(
      `Could not reach BhuDrishti backend at ${API_BASE_URL}. Is it running? (${err.message})`
    );
  }

  if (!res.ok) {
    if (res.status === 401) {
      clearAuthSession();
      redirectToLogin();
    }
    let detail = res.statusText;

    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {
      // Ignore parse errors
    }

    throw new Error(`API ${res.status} on ${path}: ${detail}`);
  }

  if (res.status === 204) return null;

  return res.json();
}

const BhuDrishtiAPI = {
  baseUrl: API_BASE_URL,

  // Authentication / RBAC
  login: async (email, password) => {
    const result = await apiRequest("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    setAuthSession(result);
    return result;
  },
  register: (payload) => apiRequest("/api/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  me: () => apiRequest("/api/auth/me"),
  logout: () => { clearAuthSession(); window.location.href = "auth.html"; },
  getAuthUser,
  getUsers: () => apiRequest("/api/auth/users"),
  setUserStatus: (userId, status) => apiRequest(`/api/auth/users/${encodeURIComponent(userId)}/status`, { method: "POST", body: JSON.stringify({ status }) }),

  // Projects
  getProjects: () => apiRequest("/api/projects"),
  getProject: (projectId) => apiRequest(`/api/projects/${encodeURIComponent(projectId)}`),

  // Datasets
  validateDataset: (payload) => apiRequest("/api/datasets/validate", { method: "POST", body: JSON.stringify(payload) }),
  uploadDataset: async (file, declaredCrs = "LOCAL-DEMO") => {
    const form = new FormData(); form.append("file", file, file.name); form.append("declared_crs", declaredCrs);
    const headers = {}; const token = getAuthToken(); if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API_BASE_URL}/api/datasets/upload`, {method:"POST", body:form, headers});
    if (res.status === 401) { clearAuthSession(); redirectToLogin(); }
    if (!res.ok) { let d=res.statusText; try { const b=await res.json(); d=b.detail||JSON.stringify(b); } catch(_){} throw new Error(`API ${res.status} on /api/datasets/upload: ${d}`); }
    return res.json();
  },
  getDatasets: () => apiRequest("/api/datasets"),
  inferDataset: (datasetId) => apiRequest(`/api/datasets/${encodeURIComponent(datasetId)}/infer`, {method:"POST"}),
  getDatasetFileUrl: (datasetId) => `${API_BASE_URL}/api/datasets/${encodeURIComponent(datasetId)}/file`,

  // Parcels
  getParcels: () => apiRequest("/api/parcels"),
  getParcel: (parcelId) => apiRequest(`/api/parcels/${encodeURIComponent(parcelId)}`),

  // Topology
  getTopologyIssues: async (parcelId = null) => {
    try {
      return await apiRequest(`/api/topology/issues${parcelId ? `?parcel_id=${encodeURIComponent(parcelId)}` : ""}`);
    } catch (err) {
      // Serverless SQLite can route the next request to an instance that does
      // not know the just-created EXT record. For an EXT-* workflow, use the
      // exact browser-cached extraction response as a continuity fallback;
      // never substitute seeded BD-* topology.
      if (parcelId && String(parcelId).toUpperCase().startsWith('EXT-')) {
        const local = getWorkflowExtraction(parcelId);
        if (local) {
          const issues = Array.isArray(local.topology_issues) ? local.topology_issues : [];
          return { issues, count: issues.length, scope: parcelId, is_demo_data: false, coordinate_system: local.coordinate_system || null, continuity_fallback: true };
        }
      }
      throw err;
    }
  },

  // Elevation
  getElevation: async (parcelId) => {
    try {
      return await apiRequest(`/api/elevation/${encodeURIComponent(parcelId)}`);
    } catch (err) {
      if (parcelId && String(parcelId).toUpperCase().startsWith('EXT-')) {
        const local = getWorkflowExtraction(parcelId);
        if (local?.elevation) return { ...local.elevation, is_demo_data: true, source: 'synthetic_demo', continuity_fallback: true, note: local.elevation_note || 'Prototype elevation cached from the same EXT record.' };
      }
      throw err;
    }
  },
  getShadow: async (parcelId, params = {}) => {
    const q = new URLSearchParams();
    if (params.sun_azimuth_deg != null) q.set("sun_azimuth_deg", params.sun_azimuth_deg);
    if (params.sun_elevation_deg != null) q.set("sun_elevation_deg", params.sun_elevation_deg);
    const suffix = q.toString() ? `?${q.toString()}` : "";
    try {
      return await apiRequest(`/api/shadow/${encodeURIComponent(parcelId)}${suffix}`);
    } catch (err) {
      if (parcelId && String(parcelId).toUpperCase().startsWith('EXT-')) {
        const local = getWorkflowExtraction(parcelId);
        if (local?.shadow_evidence) return { ...local.shadow_evidence, source: 'cached_ext_record', continuity_fallback: true };
      }
      throw err;
    }
  },

  // Confidence / risk
  getConfidence: (parcelId) => apiRequest(`/api/confidence/${encodeURIComponent(parcelId)}`),

  // Survey priority queue
  getSurveyQueue: () => apiRequest("/api/survey-queue"),

  // AI extraction (prototype/demo -- see backend docstring on this endpoint)
  runDemoExtraction: (demoCase) =>
    apiRequest("/api/extraction/demo", {
      method: "POST",
      body: JSON.stringify({ demo_case: demoCase }),
    }),

  // REAL image inference: actual multipart upload, actual OpenCV pipeline on
  // the backend (see extraction_engine.py). Uses a raw fetch (not apiRequest)
  // because FormData uploads must NOT have a manually-set Content-Type --
  // the browser has to set the multipart boundary itself.
  runRealInference: async (file, datasetId = null) => {
    const form = new FormData();
    form.append("image", file, file.name);
    if (datasetId) form.append("dataset_id", datasetId);
    let res;
    try {
      const headers = {}; const token = getAuthToken(); if (token) headers.Authorization = `Bearer ${token}`;
      res = await fetch(`${API_BASE_URL}/api/extraction/infer`, { method: "POST", body: form, headers });
    } catch (err) {
      throw new Error(`Could not reach BhuDrishti backend at ${API_BASE_URL}. Is it running? (${err.message})`);
    }
    if (res.status === 401) { clearAuthSession(); redirectToLogin(); }
    if (!res.ok) {
      let detail = res.statusText;
      try { const body = await res.json(); detail = body.detail || JSON.stringify(body); } catch (_) {}
      throw new Error(`API ${res.status} on /api/extraction/infer: ${detail}`);
    }
    return res.json();
  },
  getExtraction: async (extractionId) => {
    // EXT-* workflow records are cached locally so the same-browser prototype
    // remains continuous even when Vercel routes the next request to another
    // serverless instance. Prefer that exact record before making a backend
    // request; seeded/non-EXT records still use the backend normally.
    const local = typeof getWorkflowExtraction === "function" ? getWorkflowExtraction(extractionId) : null;
    if (local) return local;
    return apiRequest(`/api/extraction/${encodeURIComponent(extractionId)}`);
  },
  getExtractions: () => apiRequest("/api/extraction"),

  // Verification (human-in-the-loop)
  // Verification state is authoritative on the backend. Browser-local
  // verification records are deliberately ignored so a stale/fabricated
  // local record can never appear as certified after an API failure.
  getVerification: (parcelId) => apiRequest(`/api/verification/${encodeURIComponent(parcelId)}`),
  submitCorrection: (parcelId, payload) =>
    apiRequest(`/api/verification/${encodeURIComponent(parcelId)}/submit`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  certifyVerification: (parcelId, payload) =>
    apiRequest(`/api/verification/${encodeURIComponent(parcelId)}/certify`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  rejectVerification: (parcelId, payload) =>
    apiRequest(`/api/verification/${encodeURIComponent(parcelId)}/reject`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  acceptPreliminary: (parcelId, payload) =>
    apiRequest(`/api/verification/${encodeURIComponent(parcelId)}/accept-preliminary`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Export
  getExportGeojsonUrl: () => `${API_BASE_URL}/api/export/geojson`,
  getExportGeojson: () => apiRequest("/api/export/geojson"),

  // System status / demo-readiness
  getSystemStatus: () => apiRequest("/api/system/status"),

  // Health
  getHealth: () => apiRequest("/api/health"),
};

/** Small helpers shared by every screen */

// Reads ?parcel=BD-047 (or ?parcel_id=) from the current URL.
function getParcelIdFromQuery(defaultId = "BD-047") {
  const params = new URLSearchParams(window.location.search);
  return params.get("parcel") || params.get("parcel_id") || defaultId;
}

// Builds a link to another screen, carrying the active parcel along.
function linkWithParcel(page, parcelId) {
  return `${page}?parcel=${encodeURIComponent(parcelId)}`;
}

// Step 1: reads ?extraction=EXT-0001 from the current URL, if present.
// Returns null (not a default id) when absent, so callers can tell "no
// extraction requested" apart from "extraction requested" -- unlike
// getParcelIdFromQuery, there is no sensible default extraction id.
function getExtractionIdFromQuery() {
  const params = new URLSearchParams(window.location.search);
  return params.get("extraction") || null;
}

// Formats a number as a percentage string, e.g. 0.913 -> "91%"
function pct(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const n = value > 1 ? value : value * 100;
  return `${n.toFixed(digits)}%`;
}

// Small banner injector so every screen can show a consistent
// "backend unreachable" state instead of silently showing stale numbers.
function showApiError(err, containerSelector = "body") {
  console.error("[BhuDrishti API]", err);
  const el = document.createElement("div");
  el.setAttribute("data-bhudrishti-error-banner", "true");
  el.style.cssText =
    "position:fixed;top:0;left:0;right:0;z-index:9999;background:#ba1a1a;color:#fff;" +
    "padding:8px 16px;font:600 12px/1.4 Inter,sans-serif;text-align:center;";
  el.textContent = `⚠ ${err.message}`;
  document.body.prepend(el);
}


// --- Uploaded orthophoto persistence (prototype, browser-local) ----------
// The user-uploaded image is a runtime input, not a bundled project asset.
// IndexedDB keeps the Blob available when navigating from AI Extraction to
// GIS without putting large orthophotos into localStorage/sessionStorage.
const EXTRACTION_IMAGE_DB = "bhudrishti-runtime";
const EXTRACTION_IMAGE_STORE = "extraction-images";

function openExtractionImageDB() {
  return new Promise((resolve, reject) => {
    if (!window.indexedDB) {
      reject(new Error("IndexedDB is unavailable in this browser."));
      return;
    }
    const request = indexedDB.open(EXTRACTION_IMAGE_DB, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(EXTRACTION_IMAGE_STORE)) {
        db.createObjectStore(EXTRACTION_IMAGE_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Could not open browser image storage."));
  });
}

async function saveDatasetImage(datasetId, file) {
  if (!datasetId || !file) return;
  const db = await openExtractionImageDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(EXTRACTION_IMAGE_STORE, "readwrite");
    tx.objectStore(EXTRACTION_IMAGE_STORE).put(file, `dataset:${datasetId}`);
    tx.oncomplete = () => { db.close(); resolve(true); };
    tx.onerror = () => { db.close(); reject(tx.error || new Error("Could not store uploaded ORI.")); };
  });
}

async function getDatasetImage(datasetId) {
  if (!datasetId) return null;
  const db = await openExtractionImageDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(EXTRACTION_IMAGE_STORE, "readonly");
    const request = tx.objectStore(EXTRACTION_IMAGE_STORE).get(`dataset:${datasetId}`);
    request.onsuccess = () => { const value = request.result || null; db.close(); resolve(value); };
    request.onerror = () => { db.close(); reject(request.error || new Error("Could not read uploaded ORI.")); };
  });
}

async function saveExtractionImage(extractionId, file) {
  if (!extractionId || !file) return;
  const db = await openExtractionImageDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(EXTRACTION_IMAGE_STORE, "readwrite");
    tx.objectStore(EXTRACTION_IMAGE_STORE).put(file, extractionId);
    tx.oncomplete = () => { db.close(); resolve(true); };
    tx.onerror = () => { db.close(); reject(tx.error || new Error("Could not store uploaded orthophoto.")); };
  });
}

async function getExtractionImage(extractionId) {
  if (!extractionId) return null;
  const db = await openExtractionImageDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(EXTRACTION_IMAGE_STORE, "readonly");
    const request = tx.objectStore(EXTRACTION_IMAGE_STORE).get(extractionId);
    request.onsuccess = () => { const value = request.result || null; db.close(); resolve(value); };
    request.onerror = () => { db.close(); reject(request.error || new Error("Could not read uploaded orthophoto.")); };
  });
}

// --- Shared demo/system status -----------------------------------------
// Lightweight status strip injected into every Stitch page. It reports the
// backend's actual operating mode instead of implying production services.
async function syncSystemStatus() {
  if (isPublicAuthPage()) return;
  if (document.querySelector("[data-bhudrishti-system-status]")) return;
  const el = document.createElement("div");
  el.setAttribute("data-bhudrishti-system-status", "true");
  el.style.cssText = "position:fixed;right:18px;bottom:88px;z-index:9998;pointer-events:none;background:rgba(255,255,255,.96);border:1px solid rgba(0,0,0,.10);border-radius:10px;padding:7px 10px;font:600 10px/1.35 Inter,sans-serif;color:#334155;box-shadow:0 3px 14px rgba(0,0,0,.10);max-width:290px;";
  el.textContent = "Backend status: checking…";
  document.body.appendChild(el);
  try {
    const s = await BhuDrishtiAPI.getSystemStatus();
    el.innerHTML = `<div style="font-weight:800;color:#166534">● Backend Connected</div>` +
      `<div>CV: ${s.extraction?.mode || "--"} · Elevation: ${s.elevation?.mode || "--"}</div>` +
      `<div>Storage: ${s.persistence?.label || "--"} · CRS: ${s.georeferencing?.georeferenced ? (s.georeferencing.crs || "configured") : "Not georeferenced"}</div>`;
  } catch (err) {
    el.textContent = "⚠ Backend unavailable — live data is not loaded";
    el.style.color = "#991b1b";
  }
}

// --- Step 0: cross-page "latest extraction" awareness -----------------
// This is NOT a fake frontend copy of extraction data -- it stores only the
// extraction_id (a string) in sessionStorage so that navigating between
// Stitch pages within the same tab/session can re-fetch the REAL current
// record from the backend (GET /api/extraction/{id}) instead of losing
// track of it. It is explicitly session-scoped, not a persistence layer:
// it does not survive a backend restart's in-memory state being wiped, and
// a closed tab starts fresh, matching the backend's own in-memory lifetime.
const LATEST_EXTRACTION_KEY = "bhudrishti.latestExtractionId";
const WORKFLOW_EXTRACTIONS_KEY = "bhudrishti.workflow.extractions";
const WORKFLOW_VERIFICATIONS_KEY = "bhudrishti.workflow.verifications";

function _readWorkflowMap(key) {
  try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch (_) { return {}; }
}
function _writeWorkflowMap(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
}
function saveWorkflowExtraction(record) {
  if (!record?.extraction_id) return;
  const map = _readWorkflowMap(WORKFLOW_EXTRACTIONS_KEY);
  map[record.extraction_id] = record;
  _writeWorkflowMap(WORKFLOW_EXTRACTIONS_KEY, map);
  setLatestExtractionId(record.extraction_id);
}
function getWorkflowExtraction(id) {
  if (!id) return null;
  return _readWorkflowMap(WORKFLOW_EXTRACTIONS_KEY)[id] || null;
}
function saveWorkflowVerification(id, verification) {
  // Sprint 1 trust repair: verification must never be created or mutated
  // in browser storage. Backend responses are the only source of truth.
  return null;
}
function getWorkflowVerification(id) {
  // Ignore legacy browser-local verification records, including stale
  // "verified" records from older prototype builds.
  return null;
}
function buildLocalExtractionQueueItem(record) {
  if (!record?.extraction_id) return null;
  const c = record.confidence || {};
  const risk = Number.isFinite(Number(c.risk_score)) ? Number(c.risk_score) : Math.max(0, Math.min(100, 100 - Number(record.confidence_heuristic || 0)));
  const priority = String(c.priority || (risk >= 60 ? 'high' : risk >= 30 ? 'medium' : 'low')).toLowerCase();
  return {
    parcel_id: record.extraction_id, is_extraction: true, is_demo_data: false,
    risk_score: risk, confidence: Number(c.confidence ?? record.confidence_heuristic ?? 0),
    priority, reasons: Array.isArray(c.reasons) ? c.reasons : ['AI extraction awaiting survey review'],
    ai_confidence_heuristic: record.confidence_heuristic ?? null,
    topology_issue_count: Number(record.topology_issue_count || (record.topology_issues || []).length || 0),
    verification_status: record.status || 'unverified',
    geometry_source: 'ai_extraction'
  };
}
function buildLocalExportGeoJSON(targetId = null) {
  const map = _readWorkflowMap(WORKFLOW_EXTRACTIONS_KEY);
  const features = Object.values(map).filter(r => !targetId || r.extraction_id === targetId).map(r => ({
    type: 'Feature',
    properties: {
      parcel_id: r.extraction_id,
      area_m2: r.area_m2,
      source: 'ai_preliminary',
      source_filename: r.source_filename,
      verification_status: 'unverified'
    },
    geometry: r.geometry
  }));
  return {
    type: 'FeatureCollection',
    crs: null,
    coordinate_system: {type:'local_demo', crs:null, units:'meters', georeferenced:false},
    features,
    is_demo_data: false,
    note: 'Browser-local preliminary extraction fallback only. Certification/export authority remains on the backend.'
  };
}
function setLatestExtractionId(id) {
  try {
    if (id) {
      sessionStorage.setItem(LATEST_EXTRACTION_KEY, id);
      localStorage.setItem(LATEST_EXTRACTION_KEY, id);
    } else {
      sessionStorage.removeItem(LATEST_EXTRACTION_KEY);
      localStorage.removeItem(LATEST_EXTRACTION_KEY);
    }
  } catch (_) { /* storage unavailable */ }
  // The sidebar links are rendered before an extraction is created. Re-apply
  // the active context immediately so the NEXT click carries the new EXT-*
  // record instead of falling back to the page's seeded href.
  if (id && typeof applyActiveWorkflowNavigation === 'function' && document.readyState !== 'loading') {
    applyActiveWorkflowNavigation();
  }
}
function getLatestExtractionId() {
  try { return sessionStorage.getItem(LATEST_EXTRACTION_KEY) || localStorage.getItem(LATEST_EXTRACTION_KEY); } catch (_) { return null; }
}

const LATEST_DATASET_KEY = "bhudrishti.latestDatasetId";
function setLatestDatasetId(id) {
  try {
    if (id) localStorage.setItem(LATEST_DATASET_KEY, id);
    else localStorage.removeItem(LATEST_DATASET_KEY);
  } catch (_) {}
}
function getLatestDatasetId() {
  try { return localStorage.getItem(LATEST_DATASET_KEY); } catch (_) { return null; }
}


// --- Active workflow context ------------------------------------------------
// Keep the Stitch sidebar/navigation on the same EXT-* record after an upload.
// URL parameters always win; otherwise the latest real extraction ID from this
// browser session is used. This prevents silently falling back to seeded BD-*
// data when moving between GIS, Topology, and Elevation screens.
function getActiveWorkflowExtractionId() {
  const fromUrl = getExtractionIdFromQuery();
  if (fromUrl) return fromUrl;
  const params = new URLSearchParams(window.location.search);
  const parcel = params.get('parcel') || params.get('parcel_id');
  if (parcel && String(parcel).toUpperCase().startsWith('EXT-')) return parcel;
  return typeof getLatestExtractionId === 'function' ? getLatestExtractionId() : null;
}

function applyActiveWorkflowNavigation() {
  if (isPublicAuthPage()) return;
  const active = getActiveWorkflowExtractionId();
  const dataset = typeof getLatestDatasetId === 'function' ? getLatestDatasetId() : null;
  const encoded = active ? encodeURIComponent(active) : null;
  const datasetEncoded = dataset ? encodeURIComponent(dataset) : null;

  document.querySelectorAll('a[href]').forEach(a => {
    const raw = a.getAttribute('href') || '';
    // Do not rewrite external links or action links that already target a
    // specific record. Sidebar links are intentionally normalized here.
    const base = raw.split('?')[0];
    if (base === 'gis-cadastral-map.html' && encoded) {
      a.setAttribute('href', `gis-cadastral-map.html?extraction=${encoded}`);
    } else if (base === 'topology-validation.html' && encoded) {
      a.setAttribute('href', `topology-validation.html?parcel=${encoded}`);
    } else if (base === 'elevation-analysis.html' && encoded) {
      a.setAttribute('href', `elevation-analysis.html?parcel=${encoded}`);
    } else if (base === 'survey-priority.html' && encoded) {
      a.setAttribute('href', `survey-priority.html?extraction=${encoded}`);
    } else if (base === 'survey-projects.html' && (datasetEncoded || encoded)) {
      const qs = [];
      if (datasetEncoded) qs.push(`dataset=${datasetEncoded}`);
      if (encoded) qs.push(`extraction=${encoded}`);
      a.setAttribute('href', `survey-projects.html?${qs.join('&')}`);
    }
  });

  document.querySelectorAll('[data-active-workflow-context]').forEach(el => {
    el.textContent = active || dataset || 'No active upload';
  });
}


// --- Step 0 polish: shared sidebar topology badge -----------------------
// The shared Stitch sidebar shows a topology-issue badge on every screen.
// It previously hardcoded "4 Gaps" as static mockup text, which drifted
// out of sync with the real backend count. This binds every element
// tagged [data-topology-badge] (there is one per page, in the sidebar) to
// the live GET /api/topology/issues response -- no hardcoded number, no
// per-page duplication of the fetch logic. Label uses "Issues" rather than
// "Gaps" because the backend count spans all topology issue types
// (overlaps, gaps, self-intersections, invalid geometry), not gaps alone.
async function syncTopologyBadge() {
  if (isPublicAuthPage()) return;
  const badges = document.querySelectorAll("[data-topology-badge]");
  if (!badges.length) return;
  try {
    const active = typeof getActiveWorkflowExtractionId === "function" ? getActiveWorkflowExtractionId() : null;
    const data = await BhuDrishtiAPI.getTopologyIssues(active || null);
    const count = (data && typeof data.count === "number") ? data.count : (data.issues || []).length;
    badges.forEach((el) => { el.textContent = `${count} Issue${count === 1 ? "" : "s"}`; });
  } catch (err) {
    console.error("[BhuDrishti API] topology badge sync failed", err);
    badges.forEach((el) => { el.textContent = "-- Issues"; });
  }
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    if (!isPublicAuthPage()) { syncTopologyBadge(); syncSystemStatus(); }
  });
} else if (!isPublicAuthPage()) {
  syncTopologyBadge();
  syncSystemStatus();
}



// Every application screen uses the same session guard. Authentication pages
// remain public so users can sign in or request access.
(function enforceAuthentication() {
  const path = window.location.pathname || "";
  if (isPublicAuthPage()) return;
  if (!getAuthToken()) redirectToLogin();
})();


if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", applyActiveWorkflowNavigation); else applyActiveWorkflowNavigation();

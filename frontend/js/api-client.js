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
const PRODUCTION_API_BASE = "https://bhudrishti-api.vercel.app";

const API_BASE_URL =
  window.BHUDRISHTI_API_BASE ||
  (window.location.protocol === "file:" ||
   window.location.hostname === "localhost" ||
   window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : PRODUCTION_API_BASE);

async function apiRequest(path, options = {}) {
  const url = `${API_BASE_URL}${path}`;

  const fetchOptions = {
    ...options,
    headers: {
      ...(options.headers || {}),
    },
  };

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

  // Projects
  getProjects: () => apiRequest("/api/projects"),
  getProject: (projectId) => apiRequest(`/api/projects/${encodeURIComponent(projectId)}`),

  // Datasets
  validateDataset: (payload) => apiRequest("/api/datasets/validate", { method: "POST", body: JSON.stringify(payload) }),
  uploadDataset: async (file, declaredCrs = "LOCAL-DEMO") => {
    const form = new FormData(); form.append("file", file, file.name); form.append("declared_crs", declaredCrs);
    const res = await fetch(`${API_BASE_URL}/api/datasets/upload`, {method:"POST", body:form});
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
  getTopologyIssues: (parcelId = null) => apiRequest(`/api/topology/issues${parcelId ? `?parcel_id=${encodeURIComponent(parcelId)}` : ""}`),

  // Elevation
  getElevation: (parcelId) => apiRequest(`/api/elevation/${encodeURIComponent(parcelId)}`),

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
      res = await fetch(`${API_BASE_URL}/api/extraction/infer`, { method: "POST", body: form });
    } catch (err) {
      throw new Error(`Could not reach BhuDrishti backend at ${API_BASE_URL}. Is it running? (${err.message})`);
    }
    if (!res.ok) {
      let detail = res.statusText;
      try { const body = await res.json(); detail = body.detail || JSON.stringify(body); } catch (_) {}
      throw new Error(`API ${res.status} on /api/extraction/infer: ${detail}`);
    }
    return res.json();
  },
  getExtraction: (extractionId) => apiRequest(`/api/extraction/${encodeURIComponent(extractionId)}`),
  getExtractions: () => apiRequest("/api/extraction"),

  // Verification (human-in-the-loop)
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
function setLatestExtractionId(id) {
  try { sessionStorage.setItem(LATEST_EXTRACTION_KEY, id); } catch (_) { /* storage unavailable */ }
}
function getLatestExtractionId() {
  try { return sessionStorage.getItem(LATEST_EXTRACTION_KEY); } catch (_) { return null; }
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
  const badges = document.querySelectorAll("[data-topology-badge]");
  if (!badges.length) return;
  try {
    const data = await BhuDrishtiAPI.getTopologyIssues();
    const count = (data && typeof data.count === "number") ? data.count : (data.issues || []).length;
    badges.forEach((el) => { el.textContent = `${count} Issue${count === 1 ? "" : "s"}`; });
  } catch (err) {
    console.error("[BhuDrishti API] topology badge sync failed", err);
    badges.forEach((el) => { el.textContent = "-- Issues"; });
  }
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => { syncTopologyBadge(); syncSystemStatus(); });
} else {
  syncTopologyBadge();
  syncSystemStatus();
}


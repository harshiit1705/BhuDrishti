# BhuDrishti — Urban Cadastral AI

> AI-assisted urban cadastral mapping and surveyor-in-the-loop land-record workflow.

BhuDrishti is a prototype geospatial intelligence platform designed to support
urban cadastral workflows by combining aerial imagery, computer vision,
spatial validation, elevation analysis, surveyor verification, and cadastral
export into a single workflow.

## 🚀 Core Workflow

Dashboard
→ Survey Project
→ ORI / Orthophoto Upload
→ AI Feature Extraction
→ Preliminary Parcel Geometry
→ GIS Visualization
→ Topology Validation
→ Elevation Analysis
→ Survey Priority
→ Field Verification
→ Certification
→ Cadastral Export

## ✨ Key Features

- Orthophoto / aerial imagery ingestion
- Prototype OpenCV-based parcel extraction
- AI-generated preliminary parcel candidates
- Building / roof footprint detection
- GIS visualization
- Topology and geometry validation
- Elevation analysis prototype
- Confidence and survey-risk assessment
- Survey priority queue
- Human-in-the-loop boundary editing
- Surveyor certification workflow
- Verified geometry persistence
- GeoJSON cadastral export
- SQLite-backed prototype persistence
- Frontend/backend synchronization

## 🏗️ Architecture

Frontend
- HTML
- CSS
- JavaScript
- GIS-oriented UI

Backend
- Python
- FastAPI
- OpenCV
- SQLite
- Geometry processing

## 🔄 Cadastral Workflow

ORI Imagery
↓
Computer Vision
↓
Preliminary Parcel Candidates
↓
Spatial Intelligence
↓
Confidence / Risk
↓
Survey Priority
↓
Surveyor Verification
↓
Certification
↓
Verified Geometry
↓
GeoJSON Export

## ⚠️ Prototype Status

BhuDrishti is a prototype intended for demonstration and evaluation.

The current computer-vision pipeline generates preliminary image-derived
geometry. It does not represent legally authoritative cadastral boundaries.

The prototype currently operates in local-demo coordinates and does not claim
production CRS/georeferencing or direct government-record integration.

## 🛠️ Local Development

### Backend

```bash
cd backend
python -m uvicorn app.main:app --reload
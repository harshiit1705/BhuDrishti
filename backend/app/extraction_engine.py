"""
BhuDrishti Extraction Engine -- REAL, EXECUTABLE image ingestion + inference.

Honesty note (read before touching this file): this is a PROTOTYPE classical
computer-vision pipeline, not a trained neural segmentation model. It is:

    image bytes -> PIL decode -> grayscale -> Gaussian blur ->
    Otsu threshold -> morphological cleanup -> contour detection ->
    multiple candidate polygons -> prototype roof-footprint inference.
    The largest candidate remains the canonical EXT-* geometry used by
    existing downstream APIs, while the additional candidates are additive
    image-space vectors for GIS inspection.

Every step actually runs against the uploaded image's pixels. Two different
input images WILL generally produce different output geometry, because the
threshold/contour result depends on the image content, not a lookup table.

It is explicitly NOT YOLOv8, NOT a trained building-footprint model, and
reports no accuracy/mIoU numbers, because none have been measured. Call it
"Prototype Computer Vision" everywhere it is surfaced to the user.
"""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image, UnidentifiedImageError
import cv2
from shapely.geometry import Polygon
from shapely.validation import explain_validity

MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB prototype upload limit
MAX_DIMENSION = 4096                # reject absurdly large images outright
ALLOWED_FORMATS = {"PNG", "JPEG", "TIFF"}

# Demo pixel-to-metre transform used ONLY because uploaded prototype images
# carry no real georeferencing. This is a documented, fixed, made-up scale --
# NOT a real ground sampling distance measured from any sensor.
DEMO_GSD_M_PER_PX = 0.05  # "0.05 m/pixel" demo constant, disclosed to the UI
# Demo local anchor used only to make extracted geometry dimensions stable
# within this prototype. Uploaded images have NO georeferencing, so this
# coordinate space must never be interpreted as the seeded cadastral CRS or
# used to compare independent uploads against one another.
DEMO_ANCHOR_X = 40.0
DEMO_ANCHOR_Y = 20.0
DEMO_FOOTPRINT_TARGET_M = 10.0  # normalize extracted shape to roughly this span


class ImageDecodeError(ValueError):
    pass


class InferenceError(ValueError):
    pass


@dataclass
class InferenceResult:
    geometry: Polygon                # primary candidate in DEMO LOCAL METRES
    pixel_polygon: list               # primary candidate raw [(x_px, y_px), ...]
    parcel_candidates: list           # multiple candidate parcel vectors in image space
    roof_footprints: list             # prototype roof-footprint vectors in image space
    image_width: int
    image_height: int
    image_format: str
    contour_area_px: float
    confidence_heuristic: float       # 0-100, derived from actual image metrics, not fixed
    inference_mode: str = "PROTOTYPE_CV"
    notes: str = ""


def decode_image(raw_bytes: bytes, filename: str = "") -> Image.Image:
    if not raw_bytes:
        raise ImageDecodeError("No image data received.")
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise ImageDecodeError(
            f"Image is {len(raw_bytes)/1e6:.1f} MB, exceeds the {MAX_IMAGE_BYTES/1e6:.0f} MB prototype limit."
        )
    try:
        img = Image.open(BytesIO(raw_bytes))
        img.load()  # force full decode now, so corrupt files fail here, not later
    except (UnidentifiedImageError, OSError) as e:
        raise ImageDecodeError(f"Could not decode '{filename}' as an image: {e}")

    fmt = (img.format or "").upper()
    if fmt not in ALLOWED_FORMATS:
        raise ImageDecodeError(
            f"Unsupported image format '{fmt}' for '{filename}'. Accepted: {', '.join(sorted(ALLOWED_FORMATS))}."
        )
    if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
        raise ImageDecodeError(
            f"Image dimensions {img.width}x{img.height} exceed the {MAX_DIMENSION}px prototype limit."
        )
    if img.width < 8 or img.height < 8:
        raise ImageDecodeError(f"Image too small to process ({img.width}x{img.height}).")

    return img.convert("RGB")


def run_cv_inference(img: Image.Image) -> InferenceResult:
    """
    Real, executable classical-CV prototype. It segments the uploaded pixels,
    vectorizes several sufficiently large connected contours when present, and
    derives an inset roof-footprint candidate from the same foreground mask.

    This is NOT a trained cadastral/building segmentation model. The returned
    parcel candidates are preliminary image-derived candidates, not legal
    boundaries. Confidence is an extraction-quality heuristic, not accuracy.
    """
    rgb = np.array(img)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    otsu_thresh, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)

    image_area_px = float(img.width * img.height)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = _extract_candidate_contours(contours, img.width, img.height)

    # If thresholding makes the frame itself the only foreground object, use
    # edge structure as a second, still image-derived segmentation signal.
    if len(candidates) == 1 and cv2.contourArea(candidates[0]) > 0.80 * image_area_px:
        edges = cv2.Canny(blurred, 40, 120)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
        edge_contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        edge_candidates = _extract_candidate_contours(edge_contours, img.width, img.height)
        if edge_candidates:
            candidates = edge_candidates

    if not candidates:
        raise InferenceError(
            "No detectable region found after thresholding/contour extraction. "
            "Try an image with clearer boundary contrast."
        )

    candidate_records = []
    roof_records = []
    for idx, contour in enumerate(candidates, 1):
        area_px = float(cv2.contourArea(contour))
        perimeter = cv2.arcLength(contour, True)
        epsilon = max(0.005 * perimeter, 1.0)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        pts = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]
        if len(pts) < 3:
            continue
        confidence = _contour_confidence(contour, area_px, len(pts), image_area_px)
        candidate_geometry = _pixel_polygon_to_demo_geometry(pts, img.width, img.height)
        candidate_records.append({
            "candidate_id": f"P{idx:02d}",
            "pixel_polygon": pts,
            "geometry": {"type": "Polygon", "coordinates": [list(map(list, candidate_geometry.exterior.coords))]},
            "area_px": round(area_px, 1),
            "area_m2": round(candidate_geometry.area, 2),
            "vertex_count": len(pts),
            "extraction_confidence": confidence,
            "confidence_level": _confidence_level(confidence),
            "source": "prototype_cv",
            "status": "ai_preliminary",
        })

        roof_pts = _roof_footprint_from_mask(closed, contour)
        if roof_pts and len(roof_pts) >= 3:
            roof_geometry = _pixel_polygon_to_demo_geometry(roof_pts, img.width, img.height)
            roof_records.append({
                "roof_id": f"R{idx:02d}",
                "candidate_id": f"P{idx:02d}",
                "pixel_polygon": roof_pts,
                "geometry": {"type": "Polygon", "coordinates": [list(map(list, roof_geometry.exterior.coords))]},
                "vertex_count": len(roof_pts),
                "area_m2": round(roof_geometry.area, 2),
                "source": "prototype_cv_inset_mask",
                "status": "prototype_inference",
                "method": "foreground-mask erosion; not a trained roof segmentation model",
            })

    if not candidate_records:
        raise InferenceError("Detected contours could not be converted into usable polygon candidates.")

    # Largest candidate remains the canonical extraction geometry for existing
    # downstream APIs. New candidates are additive and do not break EXT IDs.
    primary = candidate_records[0]
    primary_pts = primary["pixel_polygon"]
    contour_area_px = primary["area_px"]
    geometry = _pixel_polygon_to_demo_geometry(primary_pts, img.width, img.height)
    fill_ratio = contour_area_px / image_area_px
    compactness = _compactness(candidates[0], contour_area_px)
    confidence = primary["extraction_confidence"]

    return InferenceResult(
        geometry=geometry,
        pixel_polygon=primary_pts,
        parcel_candidates=candidate_records,
        roof_footprints=roof_records,
        image_width=img.width,
        image_height=img.height,
        image_format=(img.format or "RGB"),
        contour_area_px=contour_area_px,
        confidence_heuristic=confidence,
        notes=(
            f"Otsu threshold={otsu_thresh:.1f}, primary fill_ratio={fill_ratio:.3f}, "
            f"compactness={compactness:.3f}, candidates={len(candidate_records)}. "
            f"Candidate parcels are preliminary image-derived vectors; confidence is a "
            f"segmentation-quality heuristic, not model accuracy. Roof footprints use "
            f"foreground-mask erosion as a prototype inference. Demo transform: "
            f"{DEMO_GSD_M_PER_PX} m/pixel, anchored at local demo coords "
            f"({DEMO_ANCHOR_X}, {DEMO_ANCHOR_Y}) -- NOT real-world georeferenced coordinates."
        ),
    )


def _extract_candidate_contours(contours, img_w: int, img_h: int) -> list:
    image_area = float(img_w * img_h)
    min_area = max(64.0, 0.004 * image_area)
    max_area = 0.92 * image_area
    ranked = sorted(contours, key=cv2.contourArea, reverse=True)
    selected = []
    for contour in ranked:
        area = cv2.contourArea(contour)
        if area < min_area or area > max_area:
            continue
        peri = cv2.arcLength(contour, True)
        if peri <= 0:
            continue
        approx = cv2.approxPolyDP(contour, max(0.005 * peri, 1.0), True)
        if len(approx) < 3:
            continue
        # Avoid returning nested duplicates of the same connected region.
        if any(cv2.contourArea(cv2.convexHull(contour)) > 0 and
               cv2.pointPolygonTest(other, (float(contour[0][0][0]), float(contour[0][0][1])), False) >= 0
               for other in selected):
            continue
        selected.append(contour)
        if len(selected) >= 8:
            break
    return selected


def _contour_confidence(contour, area_px: float, vertices: int, image_area_px: float) -> float:
    compactness = _compactness(contour, area_px)
    fill_ratio = area_px / image_area_px
    vertex_penalty = max(0.55, 1.0 - max(0, vertices - 4) * 0.035)
    # Heuristic is intentionally bounded and transparent; it is not accuracy.
    score = 100.0 * (0.55 * compactness + 0.25 * min(fill_ratio * 4.0, 1.0) + 0.20 * vertex_penalty)
    return round(max(0.0, min(100.0, score)), 1)


def _confidence_level(value: float) -> str:
    if value >= 80:
        return "high"
    if value >= 60:
        return "medium"
    return "low"


def _roof_footprint_from_mask(mask: np.ndarray, contour) -> list | None:
    """Create a visually distinct roof candidate from actual mask pixels.

    The operation is deliberately labelled as prototype inference: it erodes
    the foreground region, then vectorizes its largest connected component.
    """
    x, y, w, h = cv2.boundingRect(contour)
    if w < 12 or h < 12:
        return None
    local = np.zeros((h, w), dtype=np.uint8)
    shifted = contour.copy()
    shifted[:, 0, 0] -= x
    shifted[:, 0, 1] -= y
    cv2.drawContours(local, [shifted], -1, 255, thickness=-1)
    radius = max(1, int(round(min(w, h) * 0.045)))
    erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
    eroded = cv2.erode(local, erode_kernel, iterations=1)
    inner_contours, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not inner_contours:
        return None
    inner = max(inner_contours, key=cv2.contourArea)
    if cv2.contourArea(inner) < 0.20 * cv2.contourArea(shifted):
        return None
    peri = cv2.arcLength(inner, True)
    approx = cv2.approxPolyDP(inner, max(0.008 * peri, 1.0), True)
    if len(approx) < 3:
        return None
    return [(float(pt[0][0] + x), float(pt[0][1] + y)) for pt in approx]

def _compactness(contour, area_px: float) -> float:
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return 0.0
    # Isoperimetric ratio: 1.0 for a perfect circle, smaller for irregular/elongated shapes.
    return float(max(0.0, min(1.0, (4 * np.pi * area_px) / (perimeter ** 2))))


def _pixel_polygon_to_demo_geometry(pixel_polygon: list, img_w: int, img_h: int) -> Polygon:
    """
    Normalize the pixel-space polygon to roughly DEMO_FOOTPRINT_TARGET_M
    across its longest side, then place it at the fixed demo anchor. This is
    an explicit, disclosed prototype convenience transform -- it does not
    represent real ground-sampling distance or a real coordinate reference
    system, and the API response says so.
    """
    xs = [p[0] for p in pixel_polygon]
    ys = [p[1] for p in pixel_polygon]
    px_w = max(xs) - min(xs) or 1.0
    px_h = max(ys) - min(ys) or 1.0
    scale = DEMO_FOOTPRINT_TARGET_M / max(px_w, px_h)

    min_x, min_y = min(xs), min(ys)
    coords = []
    for (x, y) in pixel_polygon:
        mx = DEMO_ANCHOR_X + (x - min_x) * scale
        # flip Y: image row 0 is the top, local demo space has Y increasing "up"
        my = DEMO_ANCHOR_Y + ((px_h - (y - min_y)) * scale)
        coords.append((round(mx, 3), round(my, 3)))

    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)  # standard Shapely self-intersection repair
        if not poly.is_valid or poly.is_empty:
            raise InferenceError(f"Generated geometry is not a valid polygon: {explain_validity(poly)}")
    if isinstance(poly, Polygon) and poly.area > 1e-9:
        return poly
    raise InferenceError("Generated geometry collapsed to zero area after cleanup.")

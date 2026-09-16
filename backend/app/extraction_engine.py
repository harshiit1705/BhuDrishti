"""
BhuDrishti Extraction Engine -- REAL, EXECUTABLE image ingestion + inference.

Honesty note (read before touching this file): this is a PROTOTYPE classical
computer-vision pipeline, not a trained neural segmentation model. It is:

    image bytes -> PIL decode -> grayscale -> Gaussian blur ->
    Otsu adaptive threshold -> morphological close ->
    OpenCV contour detection -> largest contour -> polygon
    simplification (cv2.approxPolyDP) -> pixel-space Polygon

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
    geometry: Polygon                # in DEMO LOCAL METRES (see note above)
    pixel_polygon: list               # raw [(x_px, y_px), ...] for disclosure/debug
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
    Real, executable classical CV pipeline. Runs actual OpenCV operations on
    the actual decoded pixel array -- nothing here is a lookup or a canned
    result. See module docstring for the exact step list.
    """
    rgb = np.array(img)  # (H, W, 3) uint8, real pixel data
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Otsu's method picks a threshold automatically from the actual
    # grayscale histogram of THIS image -- this is why different images
    # produce different segmentation results.
    otsu_thresh, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise InferenceError(
            "No detectable region found after thresholding/contour extraction. "
            "Try an image with clearer boundary contrast."
        )

    largest = max(contours, key=cv2.contourArea)
    contour_area_px = float(cv2.contourArea(largest))
    image_area_px = float(img.width * img.height)

    if contour_area_px < 0.002 * image_area_px:
        raise InferenceError(
            f"Largest detected region ({contour_area_px:.0f} px²) is too small relative to the "
            f"image ({image_area_px:.0f} px²) to be a plausible parcel/building boundary."
        )

    # Simplify the contour to a clean polygon (Douglas-Peucker), same
    # approach a real vectorization step would use downstream of a mask.
    perimeter = cv2.arcLength(largest, True)
    epsilon = 0.01 * perimeter
    approx = cv2.approxPolyDP(largest, epsilon, True)
    pixel_polygon = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]

    if len(pixel_polygon) < 3:
        raise InferenceError("Simplified contour degenerated to fewer than 3 vertices.")

    # --- Confidence heuristic, derived from real image-analysis metrics ---
    # (NOT a fixed number, NOT a trained-model score -- an explicit,
    # disclosed heuristic combining three measurable signals.)
    fill_ratio = contour_area_px / image_area_px                     # how much of the frame the region fills
    compactness = _compactness(largest, contour_area_px)             # 1.0 = perfect circle, lower = irregular
    vertex_penalty = max(0.0, 1.0 - (len(pixel_polygon) - 4) * 0.03) # very jagged polygons score lower
    heuristic = 100.0 * max(0.0, min(1.0, 0.5 * compactness + 0.3 * min(fill_ratio * 3, 1.0) + 0.2 * vertex_penalty))

    # --- Demo pixel -> local-metre transform (documented constant, not real georeferencing) ---
    geometry = _pixel_polygon_to_demo_geometry(pixel_polygon, img.width, img.height)

    return InferenceResult(
        geometry=geometry,
        pixel_polygon=pixel_polygon,
        image_width=img.width,
        image_height=img.height,
        image_format=(img.format or "RGB"),
        contour_area_px=contour_area_px,
        confidence_heuristic=round(heuristic, 1),
        notes=(
            f"Otsu threshold={otsu_thresh:.1f}, fill_ratio={fill_ratio:.3f}, "
            f"compactness={compactness:.3f}, vertices={len(pixel_polygon)}. "
            f"Demo transform: {DEMO_GSD_M_PER_PX} m/pixel, anchored at local demo coords "
            f"({DEMO_ANCHOR_X}, {DEMO_ANCHOR_Y}) -- NOT real-world georeferenced coordinates."
        ),
    )


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

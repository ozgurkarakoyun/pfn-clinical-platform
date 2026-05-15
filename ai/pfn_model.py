"""
PFN Keypoint AI Modeli (postop AP veya LAT) - best.pt
9 anatomik keypoint tespit eder + otomatik yon
"""
import os
from pathlib import Path
from threading import Lock
from PIL import Image

_model = None
_model_lock = Lock()

MODEL_PATH = Path(__file__).parent.parent / 'models_files' / 'best.pt'

KEYPOINT_NAMES = [
    'head_center', 'head_superior', 'head_inferior',
    'head_medial', 'head_lateral', 'screw_tip',
    'neck_distal', 'shaft_proximal', 'shaft_distal'
]


def get_pfn_model():
    """Lazy load thread-safe"""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                if not MODEL_PATH.exists():
                    raise FileNotFoundError(
                        f"PFN keypoint modeli bulunamadi: {MODEL_PATH}\n"
                        f"models_files/best.pt yukleyin"
                    )
                from ultralytics import YOLO
                print(f"[PFN MODEL] Yukleniyor: {MODEL_PATH}")
                _model = YOLO(str(MODEL_PATH))
                print(f"[PFN MODEL] Hazir.")
    return _model


def _boxes_count(result):
    if result is None or getattr(result, 'boxes', None) is None:
        return 0
    return len(result.boxes)


def _best_detection_index(result):
    """Birden fazla tespit varsa confidence'ı en yüksek olanı seç."""
    if _boxes_count(result) == 0:
        return None
    try:
        return int(result.boxes.conf.argmax().item())
    except Exception:
        return 0


def _best_detection_score(result):
    idx = _best_detection_index(result)
    if idx is None:
        return 0.0
    try:
        return float(result.boxes.conf[idx])
    except Exception:
        return 0.0


def _tmp_jpeg_path(image_path, suffix):
    path = Path(image_path)
    return str(path.with_name(f"{path.stem}_{suffix}{path.suffix or '.jpg'}"))


def predict_with_auto_orientation(image_path, min_confidence=0.3):
    """Hem orijinal hem flip ile dene, yuksek confidence olani sec"""
    model = get_pfn_model()

    results_orig = model.predict(image_path, conf=min_confidence, verbose=False)

    img = Image.open(image_path)
    flipped = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    flipped_path = _tmp_jpeg_path(image_path, 'flipped_tmp')
    flipped.save(flipped_path, 'JPEG', quality=95)

    try:
        results_flip = model.predict(flipped_path, conf=min_confidence, verbose=False)
    finally:
        if os.path.exists(flipped_path):
            os.remove(flipped_path)

    result_orig = results_orig[0] if results_orig else None
    result_flip = results_flip[0] if results_flip else None
    orig_score = _best_detection_score(result_orig)
    flip_score = _best_detection_score(result_flip)

    if orig_score >= flip_score and orig_score >= min_confidence:
        return result_orig, False, orig_score
    if flip_score >= min_confidence:
        return result_flip, True, flip_score
    return None, False, 0.0


def map_keypoints_back(kp_array, image_width):
    """Flip edilmis koordinatlari orijinale geri map et"""
    mapped = kp_array.copy()
    mapped[:, 0] = (image_width - 1) - kp_array[:, 0]
    return mapped


def _extract_best_keypoints(result):
    """YOLO result içinden en güvenilir tespitin keypoint dizisini al."""
    if result is None or getattr(result, 'keypoints', None) is None:
        return None
    if len(result.keypoints) == 0:
        return None
    idx = _best_detection_index(result) or 0
    try:
        return result.keypoints.xy[idx].cpu().numpy()
    except Exception:
        return result.keypoints.xy[0].cpu().numpy()


def predict_keypoints(image_path, side='auto'):
    """9 anatomik keypoint tespit et"""
    model = get_pfn_model()
    img = Image.open(image_path)
    image_width = img.width

    side = (side or 'auto').lower()
    if side not in ('auto', 'left', 'right'):
        return {'success': False, 'error': 'side auto, left veya right olmali'}

    if side == 'auto':
        result, was_flipped, confidence = predict_with_auto_orientation(image_path)
    elif side == 'left':
        flipped = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        flipped_path = _tmp_jpeg_path(image_path, 'left_tmp')
        flipped.save(flipped_path, 'JPEG', quality=95)
        try:
            results = model.predict(flipped_path, conf=0.3, verbose=False)
        finally:
            if os.path.exists(flipped_path):
                os.remove(flipped_path)
        result = results[0] if results else None
        was_flipped = True
        confidence = _best_detection_score(result)
    else:  # right
        results = model.predict(image_path, conf=0.3, verbose=False)
        result = results[0] if results else None
        was_flipped = False
        confidence = _best_detection_score(result)

    if result is None or _boxes_count(result) == 0:
        return {
            'success': False,
            'error': 'Grafide kalca implanti tespit edilemedi'
        }

    kp_array = _extract_best_keypoints(result)
    if kp_array is None:
        return {
            'success': False,
            'error': 'Grafide keypoint tespit edilemedi'
        }

    if len(kp_array) != 9:
        return {
            'success': False,
            'error': f'9 keypoint bekleniyor, {len(kp_array)} bulundu'
        }

    if was_flipped:
        kp_array = map_keypoints_back(kp_array, image_width)

    keypoints = {}
    for i, name in enumerate(KEYPOINT_NAMES):
        keypoints[name] = [float(kp_array[i][0]), float(kp_array[i][1])]

    return {
        'success': True,
        'keypoints': keypoints,
        'detected_side': 'left' if was_flipped else 'right',
        'detection_confidence': round(confidence, 3),
        'image_width': image_width,
        'image_height': img.height,
    }

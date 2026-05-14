"""
PFN Keypoint AI Modeli (postop AP veya LAT)
best.pt'yi yukler ve 9 anatomik keypoint tespit eder.
"""
import os
from pathlib import Path
from threading import Lock
from PIL import Image
import numpy as np

_model = None
_model_lock = Lock()

MODEL_PATH = Path(__file__).parent.parent / 'models_files' / 'best.pt'

KEYPOINT_NAMES = [
    'head_center', 'head_superior', 'head_inferior',
    'head_medial', 'head_lateral', 'screw_tip',
    'neck_distal', 'shaft_proximal', 'shaft_distal'
]


def get_pfn_model():
    """Lazy load, thread-safe"""
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


def predict_with_auto_orientation(image_path, min_confidence=0.3):
    """
    Hem orijinal hem flip ile dene, yuksek confidence olani sec.
    
    Returns:
        result: YOLO result veya None
        was_flipped: bool
        confidence: float
    """
    model = get_pfn_model()
    
    results_orig = model.predict(image_path, conf=min_confidence, verbose=False)
    
    img = Image.open(image_path)
    flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
    flipped_path = str(image_path).replace('.jpg', '_flipped_tmp.jpg')
    flipped.save(flipped_path, 'JPEG', quality=95)
    
    try:
        results_flip = model.predict(flipped_path, conf=min_confidence, verbose=False)
    finally:
        if os.path.exists(flipped_path):
            os.remove(flipped_path)
    
    orig_score = 0
    flip_score = 0
    
    if results_orig and len(results_orig[0].boxes) > 0:
        orig_score = float(results_orig[0].boxes.conf.max())
    if results_flip and len(results_flip[0].boxes) > 0:
        flip_score = float(results_flip[0].boxes.conf.max())
    
    if orig_score > flip_score and orig_score > min_confidence:
        return results_orig[0], False, orig_score
    elif flip_score > min_confidence:
        return results_flip[0], True, flip_score
    return None, False, 0.0


def map_keypoints_back(kp_array, image_width):
    """Flip edilmis koordinatlari orijinale geri map et"""
    mapped = kp_array.copy()
    mapped[:, 0] = image_width - kp_array[:, 0]
    return mapped


def predict_keypoints(image_path, side='auto'):
    """
    Bir grafide 9 anatomik keypoint tespit et.
    
    Parameters:
        image_path: str
        side: 'auto' / 'right' / 'left'
    
    Returns:
        dict: {
            'success': bool,
            'keypoints': {name: [x,y]},
            'detected_side': 'right' / 'left',
            'detection_confidence': float,
            'image_width': int,
            'image_height': int,
            'error': str  # basarisiz olunca
        }
    """
    model = get_pfn_model()
    img = Image.open(image_path)
    image_width = img.width
    
    if side == 'auto':
        result, was_flipped, confidence = predict_with_auto_orientation(image_path)
    elif side == 'left':
        flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
        flipped_path = str(image_path).replace('.jpg', '_left_tmp.jpg')
        flipped.save(flipped_path, 'JPEG', quality=95)
        try:
            results = model.predict(flipped_path, conf=0.3, verbose=False)
        finally:
            if os.path.exists(flipped_path):
                os.remove(flipped_path)
        result = results[0] if results else None
        was_flipped = True
        confidence = float(result.boxes.conf.max()) if result and len(result.boxes) > 0 else 0.0
    else:  # right
        results = model.predict(image_path, conf=0.3, verbose=False)
        result = results[0] if results else None
        was_flipped = False
        confidence = float(result.boxes.conf.max()) if result and len(result.boxes) > 0 else 0.0
    
    if result is None or result.keypoints is None or len(result.keypoints) == 0:
        return {
            'success': False,
            'error': 'Grafide kalca implanti tespit edilemedi'
        }
    
    kp_array = result.keypoints.xy[0].cpu().numpy()
    
    if len(kp_array) != 9:
        return {
            'success': False,
            'error': f'9 keypoint bekleniyor, {len(kp_array)} bulundu'
        }
    
    # Flip yapildiysa orijinal koordinatlara geri map et
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

"""
AO Siniflama AI Modeli (preop) - femur_model.pt
"""
from pathlib import Path
from threading import Lock

_model = None
_model_lock = Lock()

MODEL_PATH = Path(__file__).parent.parent / 'models_files' / 'femur_model.pt'


def get_ao_model():
    """Lazy load thread-safe"""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                if not MODEL_PATH.exists():
                    raise FileNotFoundError(
                        f"AO model bulunamadi: {MODEL_PATH}\n"
                        f"models_files/femur_model.pt yukleyin"
                    )
                from ultralytics import YOLO
                print(f"[AO MODEL] Yukleniyor: {MODEL_PATH}")
                _model = YOLO(str(MODEL_PATH))
                print(f"[AO MODEL] Hazir. Siniflar: {_model.names}")
    return _model


def classify_fracture(image_path, conf_threshold=0.25):
    """
    Bir grafide AO siniflamasi yap.
    Returns dict with best_class, best_confidence, best_bbox, all_predictions
    """
    model = get_ao_model()
    results = model.predict(image_path, conf=conf_threshold, verbose=False)
    
    if not results or len(results) == 0:
        return {
            'best_class': None,
            'best_confidence': 0.0,
            'best_bbox': None,
            'all_predictions': []
        }
    
    r = results[0]
    
    if r.boxes is None or len(r.boxes) == 0:
        return {
            'best_class': 'normal',
            'best_confidence': 0.0,
            'best_bbox': None,
            'all_predictions': [{'class': 'normal', 'confidence': 0.0, 'bbox': None}]
        }
    
    boxes = r.boxes
    all_preds = []
    for i in range(len(boxes)):
        cls_idx = int(boxes.cls[i])
        conf = float(boxes.conf[i])
        bbox = boxes.xyxy[i].cpu().numpy().tolist()
        all_preds.append({
            'class': model.names[cls_idx],
            'confidence': round(conf, 4),
            'bbox': [round(x, 1) for x in bbox],
        })
    
    all_preds.sort(key=lambda x: x['confidence'], reverse=True)
    best = all_preds[0]
    
    return {
        'best_class': best['class'],
        'best_confidence': best['confidence'],
        'best_bbox': best['bbox'],
        'all_predictions': all_preds,
    }

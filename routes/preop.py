"""
Preoperatif AO Siniflama AI endpoint'i
"""
import os
import uuid
from datetime import datetime
from pathlib import Path
from io import BytesIO

from flask import Blueprint, request, jsonify, current_app
from PIL import Image, ImageOps
import numpy as np

from models import db, Patient, PreopAnalysis
from ai.ao_model import get_ao_model, classify_fracture

# DICOM destegi
try:
    import pydicom
    DICOM_AVAILABLE = True
except ImportError:
    DICOM_AVAILABLE = False

preop_bp = Blueprint('preop', __name__, url_prefix='/api/preop')

UPLOAD_DIR = Path(__file__).parent.parent / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def is_dicom(file_bytes, filename=""):
    if filename.lower().endswith(('.dcm', '.dicom')):
        return True
    return len(file_bytes) > 132 and file_bytes[128:132] == b'DICM'


def read_dicom_to_pil(file_bytes):
    if not DICOM_AVAILABLE:
        raise RuntimeError("pydicom yuklu degil")
    
    ds = pydicom.dcmread(BytesIO(file_bytes), force=True)
    pixel_array = ds.pixel_array
    
    photometric = getattr(ds, 'PhotometricInterpretation', 'MONOCHROME2')
    if photometric == 'MONOCHROME1':
        pixel_array = pixel_array.max() - pixel_array
    
    pmin, pmax = pixel_array.min(), pixel_array.max()
    if pmax > pmin:
        normalized = ((pixel_array - pmin) / (pmax - pmin) * 255).astype(np.uint8)
    else:
        normalized = np.zeros_like(pixel_array, dtype=np.uint8)
    
    if len(normalized.shape) == 2:
        pil_img = Image.fromarray(normalized, mode='L').convert('RGB')
    else:
        pil_img = Image.fromarray(normalized).convert('RGB')
    
    metadata = {
        'is_dicom': True,
        'patient_name': str(getattr(ds, 'PatientName', '')) or None,
        'patient_id': str(getattr(ds, 'PatientID', '')) or None,
        'study_date': str(getattr(ds, 'StudyDate', '')) or None,
        'modality': str(getattr(ds, 'Modality', '')) or None,
    }
    return pil_img, metadata


def load_image_from_upload(file):
    """Yuklenen dosyayi PIL Image'e cevir (DICOM dahil)"""
    file_bytes = file.read()
    
    if is_dicom(file_bytes, file.filename):
        img, _ = read_dicom_to_pil(file_bytes)
        return img
    
    img = Image.open(BytesIO(file_bytes))
    
    if img.mode in ('RGBA', 'LA', 'P'):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = bg
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    
    return img


@preop_bp.route('/<int:patient_id>/analyze', methods=['POST'])
def analyze_preop(patient_id):
    """
    Preop grafi yukle ve AO siniflamasi yap.
    Body: form-data 'image' = dosya
    """
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        if 'image' not in request.files:
            return jsonify({'error': 'Dosya yuklenmedi'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'Dosya secilmedi'}), 400
        
        # Goruntuyu yukle
        img = load_image_from_upload(file)
        
        # Diskte kaydet
        unique_id = uuid.uuid4().hex[:8]
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f'preop_{patient_id}_{timestamp}_{unique_id}.jpg'
        save_path = UPLOAD_DIR / filename
        img.save(save_path, 'JPEG', quality=90)
        
        # AI ile siniflama
        try:
            result = classify_fracture(str(save_path))
        except Exception as ai_err:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'AI hata: {str(ai_err)}'}), 500
        
        # Mevcut analiz varsa sil
        existing = PreopAnalysis.query.filter_by(patient_id=patient_id).first()
        if existing:
            old_path = UPLOAD_DIR / existing.image_filename
            if old_path.exists():
                old_path.unlink()
            db.session.delete(existing)
            db.session.flush()
        
        # Yeni kayit
        analysis = PreopAnalysis(
            patient_id=patient_id,
            image_filename=filename,
            image_width=img.width,
            image_height=img.height,
            ai_class=result.get('best_class'),
            ai_confidence=result.get('best_confidence'),
            ai_bbox=result.get('best_bbox'),
            ai_all_predictions=result.get('all_predictions', []),
        )
        db.session.add(analysis)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'analysis': analysis.to_dict(),
            'all_predictions': result.get('all_predictions', []),
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@preop_bp.route('/<int:patient_id>/correct', methods=['PUT'])
def correct_preop(patient_id):
    """AO sinifini manuel olarak duzelt"""
    try:
        analysis = PreopAnalysis.query.filter_by(patient_id=patient_id).first()
        if not analysis:
            return jsonify({'error': 'Preop analiz bulunamadi'}), 404
        
        data = request.get_json() or {}
        
        if 'manual_class' in data:
            analysis.manual_class = data['manual_class']
            analysis.manual_corrected = bool(data['manual_class'])
        
        for field in ['fracture_displacement', 'lateral_wall_integrity', 'notes']:
            if field in data:
                setattr(analysis, field, data[field])
        
        db.session.commit()
        return jsonify({'success': True, 'analysis': analysis.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@preop_bp.route('/<int:patient_id>', methods=['GET'])
def get_preop(patient_id):
    """Preop analiz bilgisini dondur"""
    analysis = PreopAnalysis.query.filter_by(patient_id=patient_id).first()
    if not analysis:
        return jsonify({'success': True, 'analysis': None})
    return jsonify({'success': True, 'analysis': analysis.to_dict()})


@preop_bp.route('/<int:patient_id>', methods=['DELETE'])
def delete_preop(patient_id):
    """Preop analizi sil"""
    try:
        analysis = PreopAnalysis.query.filter_by(patient_id=patient_id).first()
        if not analysis:
            return jsonify({'error': 'Bulunamadi'}), 404
        
        old_path = UPLOAD_DIR / analysis.image_filename
        if old_path.exists():
            old_path.unlink()
        
        db.session.delete(analysis)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

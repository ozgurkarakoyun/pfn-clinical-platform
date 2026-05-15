"""
Preoperatif AO Siniflama AI endpoint'i
"""
import uuid
from datetime import datetime
from pathlib import Path
from io import BytesIO

from flask import Blueprint, request, jsonify, session
from PIL import Image, ImageOps
import numpy as np

from models import db, Patient, PreopAnalysis
from ai.ao_model import classify_fracture

try:
    import pydicom
    DICOM_AVAILABLE = True
except ImportError:
    DICOM_AVAILABLE = False

preop_bp = Blueprint('preop', __name__, url_prefix='/api/preop')

UPLOAD_DIR = Path(__file__).parent.parent / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def require_doctor_or_admin():
    if session.get('role') not in ('doctor', 'admin'):
        return jsonify({'error': 'Giris yapmalisiniz'}), 401
    return None


def check_patient_access(patient_id):
    """Doktor sadece kendi olusturdugu hastaya erisebilir"""
    if session.get('role') == 'doctor':
        created = session.get('created_patients', [])
        if patient_id not in created:
            return jsonify({'error': 'Bu hastaya erisim yetkiniz yok'}), 403
    return None


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
    
    return pil_img


def load_image_from_upload(file):
    file_bytes = file.read()
    
    if is_dicom(file_bytes, file.filename):
        return read_dicom_to_pil(file_bytes)
    
    try:
        img = Image.open(BytesIO(file_bytes))
        img.load()
    except Exception as exc:
        raise ValueError('Gecersiz veya desteklenmeyen goruntu dosyasi') from exc
    
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
    """Preop grafi yukle ve AO siniflamasi yap"""
    auth = require_doctor_or_admin()
    if auth: return auth
    
    access = check_patient_access(patient_id)
    if access: return access
    
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        if 'image' not in request.files:
            return jsonify({'error': 'Dosya yuklenmedi'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'Dosya secilmedi'}), 400
        
        try:
            img = load_image_from_upload(file)
        except ValueError as img_err:
            return jsonify({'error': str(img_err)}), 400
        
        # Once gecici lokal save - AI'a path lazim
        import uuid as _uuid
        temp_filename = f'temp_preop_{patient_id}_{_uuid.uuid4().hex[:8]}.jpg'
        temp_path = UPLOAD_DIR / temp_filename
        img.save(temp_path, 'JPEG', quality=90)
        
        try:
            result = classify_fracture(str(temp_path))
        except Exception as ai_err:
            if temp_path.exists():
                temp_path.unlink()
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'AI hata: {str(ai_err)}'}), 500
        
        # AI bitti - simdi storage helper ile kalici kaydet
        from storage import save_image_jpg, delete_image
        try:
            storage_info = save_image_jpg(img, prefix='preop', patient_id=patient_id, quality=85)
        finally:
            # Gecici dosyayi sil
            if temp_path.exists():
                temp_path.unlink()
        
        # Mevcut analiz varsa sil (eski storage'i da)
        existing = PreopAnalysis.query.filter_by(patient_id=patient_id).first()
        if existing:
            if existing.storage_id and existing.storage_type:
                try:
                    delete_image(existing.storage_id, existing.storage_type)
                except Exception:
                    pass
            elif existing.image_filename:
                old_path = UPLOAD_DIR / existing.image_filename
                if old_path.exists():
                    old_path.unlink()
            db.session.delete(existing)
            db.session.flush()
        
        analysis = PreopAnalysis(
            patient_id=patient_id,
            image_filename=storage_info['storage_id'] if storage_info['storage_type'] == 'local' else None,
            image_url=storage_info['url'],
            storage_id=storage_info['storage_id'],
            storage_type=storage_info['storage_type'],
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
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@preop_bp.route('/<int:patient_id>/correct', methods=['PUT'])
def correct_preop(patient_id):
    """AO sinifini manuel duzelt"""
    auth = require_doctor_or_admin()
    if auth: return auth
    
    access = check_patient_access(patient_id)
    if access: return access
    
    try:
        analysis = PreopAnalysis.query.filter_by(patient_id=patient_id).first()
        if not analysis:
            return jsonify({'error': 'Preop analiz bulunamadi'}), 404
        
        data = request.get_json() or {}
        
        if 'manual_class' in data:
            analysis.manual_class = data['manual_class']
            analysis.manual_corrected = bool(data['manual_class'])
        
        db.session.commit()
        return jsonify({'success': True, 'analysis': analysis.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@preop_bp.route('/<int:patient_id>/manual', methods=['POST'])
def set_manual_preop(patient_id):
    """
    Grafi olmadan manuel AO siniflama kaydet.
    Hekim grafi yukleyemiyorsa direkt sinif secebilir.
    """
    auth = require_doctor_or_admin()
    if auth: return auth
    
    access = check_patient_access(patient_id)
    if access: return access
    
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.get_json() or {}
        
        manual_class = (data.get('manual_class') or '').strip()
        if not manual_class:
            return jsonify({'error': 'manual_class zorunlu'}), 400
        
        valid_classes = ['31-A1', '31-A2', '31-A3', '31-B', '32-A', '32-B', 'normal']
        if manual_class not in valid_classes:
            return jsonify({'error': f'Gecersiz sinif: {manual_class}'}), 400
        
        # Mevcut analiz varsa guncelle, yoksa olustur
        existing = PreopAnalysis.query.filter_by(patient_id=patient_id).first()
        
        if existing:
            # Sadece manuel sinifi guncelle
            existing.manual_class = manual_class
            existing.manual_corrected = True
            db.session.commit()
            return jsonify({'success': True, 'analysis': existing.to_dict()})
        else:
            # Yeni manuel-only analiz olustur (gorsel yok)
            analysis = PreopAnalysis(
                patient_id=patient_id,
                image_filename=None,  # Bos - grafi yok
                image_url=None,
                storage_id=None,
                storage_type=None,
                image_width=None,
                image_height=None,
                ai_class=None,
                ai_confidence=None,
                ai_bbox=None,
                ai_all_predictions=[],
                manual_class=manual_class,
                manual_corrected=True,
            )
            db.session.add(analysis)
            db.session.commit()
            return jsonify({'success': True, 'analysis': analysis.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@preop_bp.route('/<int:patient_id>', methods=['DELETE'])
def delete_preop(patient_id):
    auth = require_doctor_or_admin()
    if auth: return auth
    
    access = check_patient_access(patient_id)
    if access: return access
    
    try:
        analysis = PreopAnalysis.query.filter_by(patient_id=patient_id).first()
        if not analysis:
            return jsonify({'error': 'Bulunamadi'}), 404
        
        # Storage helper ile sil (Cloudinary veya lokal)
        if analysis.storage_id and analysis.storage_type:
            try:
                from storage import delete_image
                delete_image(analysis.storage_id, analysis.storage_type)
            except Exception:
                pass
        elif analysis.image_filename:
            # Eski sistem - sadece lokal dosya
            old_path = UPLOAD_DIR / analysis.image_filename
            if old_path.exists():
                old_path.unlink()
        
        db.session.delete(analysis)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

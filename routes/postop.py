"""
Postoperatif PFN Keypoint AI endpoint'i (AP veya LAT)
"""
import uuid
from datetime import datetime
from pathlib import Path
from io import BytesIO

from flask import Blueprint, request, jsonify, session
from PIL import Image, ImageOps
import numpy as np

from models import db, Patient, PostopAnalysis
from ai.pfn_model import predict_keypoints
from ai.geometrik_modul import compute_pfn_parameters, calculate_failure_risk

try:
    import pydicom
    DICOM_AVAILABLE = True
except ImportError:
    DICOM_AVAILABLE = False

postop_bp = Blueprint('postop', __name__, url_prefix='/api/postop')

UPLOAD_DIR = Path(__file__).parent.parent / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

KEYPOINT_NAMES = [
    'head_center', 'head_superior', 'head_inferior',
    'head_medial', 'head_lateral', 'screw_tip',
    'neck_distal', 'shaft_proximal', 'shaft_distal'
]


def require_doctor_or_admin():
    if session.get('role') not in ('doctor', 'admin'):
        return jsonify({'error': 'Giris yapmalisiniz'}), 401
    return None


def check_patient_access(patient_id):
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
    
    metadata = {
        'is_dicom': True,
        'study_date': str(getattr(ds, 'StudyDate', '')) or None,
        'modality': str(getattr(ds, 'Modality', '')) or None,
    }
    if hasattr(ds, 'PixelSpacing'):
        try:
            ps = ds.PixelSpacing
            metadata['pixel_spacing_mm'] = float(ps[0]) if hasattr(ps, '__len__') else float(ps)
        except Exception:
            metadata['pixel_spacing_mm'] = None
    
    return pil_img, metadata


def load_image_from_upload(file):
    file_bytes = file.read()
    
    if is_dicom(file_bytes, file.filename):
        img, dicom_meta = read_dicom_to_pil(file_bytes)
        return img, dicom_meta
    
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
    
    return img, None


@postop_bp.route('/<int:patient_id>/analyze', methods=['POST'])
def analyze_postop(patient_id):
    """Postop grafi yukle (AP veya LAT) ve PFN AI analizi yap"""
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
        
        view_type = request.form.get('view_type', 'AP').upper()
        if view_type not in ('AP', 'LAT'):
            return jsonify({'error': 'view_type AP veya LAT olmali'}), 400
        
        manual_side = (request.form.get('side', 'auto') or 'auto').lower()
        if manual_side not in ('auto', 'left', 'right'):
            return jsonify({'error': 'side auto, left veya right olmali'}), 400
        
        try:
            img, dicom_meta = load_image_from_upload(file)
        except ValueError as img_err:
            return jsonify({'error': str(img_err)}), 400
        
        unique_id = uuid.uuid4().hex[:8]
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f'postop_{view_type.lower()}_{patient_id}_{timestamp}_{unique_id}.jpg'
        save_path = UPLOAD_DIR / filename
        img.save(save_path, 'JPEG', quality=90)
        
        try:
            kp_result = predict_keypoints(str(save_path), side=manual_side)
        except Exception as ai_err:
            if save_path.exists():
                save_path.unlink()
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'AI hata: {str(ai_err)}'}), 500
        
        if not kp_result.get('success'):
            if save_path.exists():
                save_path.unlink()
            return jsonify({'error': kp_result.get('error', 'Keypoint tespit edilemedi')}), 400
        
        # Kalibrasyon
        pixel_spacing = 0.14
        calibration_method = 'default'
        if dicom_meta and dicom_meta.get('pixel_spacing_mm'):
            pixel_spacing = dicom_meta['pixel_spacing_mm']
            calibration_method = 'dicom'
        
        keypoints_dict = {name: tuple(kp_result['keypoints'][name]) 
                          for name in KEYPOINT_NAMES}
        
        params = compute_pfn_parameters(
            keypoints_dict,
            pixel_spacing_mm=pixel_spacing,
            D_true_mm=45.0
        )
        risk = calculate_failure_risk(params)
        
        # Mevcut ayni view_type analiz varsa sil
        existing = PostopAnalysis.query.filter_by(
            patient_id=patient_id, view_type=view_type
        ).first()
        if existing:
            old_path = UPLOAD_DIR / existing.image_filename
            if old_path.exists():
                old_path.unlink()
            db.session.delete(existing)
            db.session.flush()
        
        analysis = PostopAnalysis(
            patient_id=patient_id,
            view_type=view_type,
            image_filename=filename,
            image_width=img.width,
            image_height=img.height,
            detected_side=kp_result.get('detected_side'),
            detection_confidence=kp_result.get('detection_confidence'),
            keypoints=kp_result['keypoints'],
            apex_point=params.get('apex_point'),
            apex_method=params.get('apex_method'),
            pixel_spacing_mm=pixel_spacing,
            calibration_method=calibration_method,
            d_true_mm=45.0,
            tad_ap_mm=params.get('TAD_AP_mm') if view_type == 'AP' else None,
            tad_lat_mm=params.get('TAD_AP_mm') if view_type == 'LAT' else None,
            nsa_deg=params.get('NSA_deg'),
            cleveland_zone=params.get('Cleveland_zone'),
            parker_ap_ratio=params.get('Parker_AP_ratio'),
            parker_ml_ratio=params.get('Parker_ML_ratio'),
            femur_head_diameter_mm=params.get('femur_head_diameter_measured_mm'),
            risk_score=risk.get('risk_score'),
            risk_category=risk.get('category'),
            risk_factors=risk.get('risk_factors', []),
            dicom_metadata=dicom_meta,
        )
        db.session.add(analysis)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'analysis': analysis.to_dict(),
            'parameters': params,
            'risk': risk,
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@postop_bp.route('/<int:analysis_id>/recalculate', methods=['POST'])
def recalculate(analysis_id):
    """Manuel duzeltilmis keypoint'lerle yeniden hesapla"""
    auth = require_doctor_or_admin()
    if auth: return auth
    
    try:
        analysis = PostopAnalysis.query.get_or_404(analysis_id)
        
        access = check_patient_access(analysis.patient_id)
        if access: return access
        
        data = request.get_json() or {}
        
        keypoints_dict = {}
        kp_data = data.get('keypoints', analysis.keypoints)
        for name in KEYPOINT_NAMES:
            kp = kp_data.get(name)
            if not kp or len(kp) != 2:
                return jsonify({'error': f'Keypoint eksik: {name}'}), 400
            keypoints_dict[name] = (float(kp[0]), float(kp[1]))
        
        pixel_spacing = float(data.get('pixel_spacing_mm', analysis.pixel_spacing_mm or 0.14))
        d_true = float(data.get('d_true_mm', analysis.d_true_mm or 45.0))
        manual_apex = data.get('manual_apex')
        
        params = compute_pfn_parameters(
            keypoints_dict,
            pixel_spacing_mm=pixel_spacing,
            D_true_mm=d_true,
            manual_apex=manual_apex
        )
        risk = calculate_failure_risk(params)
        
        analysis.keypoints = {name: list(kp) for name, kp in keypoints_dict.items()}
        analysis.keypoints_manual_corrected = True
        analysis.apex_point = params.get('apex_point')
        analysis.apex_method = params.get('apex_method')
        analysis.pixel_spacing_mm = pixel_spacing
        analysis.d_true_mm = d_true
        
        if analysis.view_type == 'AP':
            analysis.tad_ap_mm = params.get('TAD_AP_mm')
        else:
            analysis.tad_lat_mm = params.get('TAD_AP_mm')
        
        analysis.nsa_deg = params.get('NSA_deg')
        analysis.cleveland_zone = params.get('Cleveland_zone')
        analysis.parker_ap_ratio = params.get('Parker_AP_ratio')
        analysis.parker_ml_ratio = params.get('Parker_ML_ratio')
        analysis.femur_head_diameter_mm = params.get('femur_head_diameter_measured_mm')
        analysis.risk_score = risk.get('risk_score')
        analysis.risk_category = risk.get('category')
        analysis.risk_factors = risk.get('risk_factors', [])
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'analysis': analysis.to_dict(),
            'parameters': params,
            'risk': risk,
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@postop_bp.route('/<int:analysis_id>', methods=['DELETE'])
def delete_postop(analysis_id):
    auth = require_doctor_or_admin()
    if auth: return auth
    
    try:
        analysis = PostopAnalysis.query.get_or_404(analysis_id)
        
        access = check_patient_access(analysis.patient_id)
        if access: return access
        
        old_path = UPLOAD_DIR / analysis.image_filename
        if old_path.exists():
            old_path.unlink()
        db.session.delete(analysis)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@postop_bp.route('/analysis/<int:analysis_id>', methods=['GET'])
def get_analysis(analysis_id):
    """Tek bir postop analiz detayini dondur (interaktif gozden gecirici icin)"""
    auth = require_doctor_or_admin()
    if auth: return auth
    
    try:
        analysis = PostopAnalysis.query.get_or_404(analysis_id)
        
        access = check_patient_access(analysis.patient_id)
        if access: return access
        
        return jsonify({'success': True, 'analysis': analysis.to_dict()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@postop_bp.route('/<int:patient_id>/combined', methods=['GET'])
def combined_tad(patient_id):
    """Toplam TAD (AP + LAT) hesabi"""
    auth = require_doctor_or_admin()
    if auth: return auth
    
    access = check_patient_access(patient_id)
    if access: return access
    
    try:
        ap_analyses = PostopAnalysis.query.filter_by(
            patient_id=patient_id, view_type='AP'
        ).order_by(PostopAnalysis.created_at.desc()).all()
        
        lat_analyses = PostopAnalysis.query.filter_by(
            patient_id=patient_id, view_type='LAT'
        ).order_by(PostopAnalysis.created_at.desc()).all()
        
        ap = ap_analyses[0] if ap_analyses else None
        lat = lat_analyses[0] if lat_analyses else None
        
        result = {
            'has_ap': ap is not None,
            'has_lat': lat is not None,
            'tad_ap_mm': ap.tad_ap_mm if ap else None,
            'tad_lat_mm': lat.tad_lat_mm if lat else None,
            'tad_total_mm': None,
            'method': None,
            'risk_threshold_mm': None,
            'over_threshold': None,
        }
        
        if ap and lat and ap.tad_ap_mm is not None and lat.tad_lat_mm is not None:
            total = ap.tad_ap_mm + lat.tad_lat_mm
            result.update({
                'tad_total_mm': round(total, 2),
                'method': 'baumgaertner_complete',
                'risk_threshold_mm': 25,
                'over_threshold': total > 25,
            })
        elif ap and ap.tad_ap_mm is not None:
            result.update({
                'method': 'ap_only',
                'risk_threshold_mm': 15,
                'over_threshold': ap.tad_ap_mm > 15,
            })
        
        return jsonify({'success': True, 'combined': result})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

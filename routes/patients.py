"""
Sadelestirilmis Hasta CRUD endpoint'leri.
- Doktor: sadece kendi olusturdugu hastalari gorebilir
- Admin: tum hastalara erisim
"""
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, session
from models import db, Patient

UPLOAD_DIR = Path(__file__).parent.parent / 'static' / 'uploads'
VALID_SEX = {'M', 'F'}
VALID_SIDE = {'right', 'left'}
VALID_OUTCOME = {'pending', 'union', 'failure'}


def _parse_patient_payload(data, *, partial=False):
    """Hasta verisini doğrula ve normalize et. Hatalarda (None, mesaj) döner."""
    cleaned = {}

    if not partial or 'age' in data:
        if data.get('age') is None or data.get('age') == '':
            return None, 'Yas zorunlu'
        try:
            age = int(data.get('age'))
        except (TypeError, ValueError):
            return None, 'Yas sayisal olmali'
        if age < 0 or age > 120:
            return None, 'Yas 0-120 arasinda olmali'
        cleaned['age'] = age

    if not partial or 'sex' in data:
        sex = data.get('sex')
        if not sex:
            return None, 'Cinsiyet zorunlu'
        if sex not in VALID_SEX:
            return None, 'Cinsiyet M veya F olmali'
        cleaned['sex'] = sex

    if not partial or 'side' in data:
        side = data.get('side')
        if not side:
            return None, 'Taraf zorunlu'
        if side not in VALID_SIDE:
            return None, 'Taraf right veya left olmali'
        cleaned['side'] = side

    if 'outcome' in data or not partial:
        outcome = data.get('outcome', 'pending') or 'pending'
        if outcome not in VALID_OUTCOME:
            return None, 'Outcome pending, union veya failure olmali'
        cleaned['outcome'] = outcome

    if 'nail_brand' in data or not partial:
        nail_brand = data.get('nail_brand')
        cleaned['nail_brand'] = nail_brand.strip() if isinstance(nail_brand, str) and nail_brand.strip() else None

    if 'outcome_notes' in data or not partial:
        outcome_notes = data.get('outcome_notes')
        cleaned['outcome_notes'] = outcome_notes.strip() if isinstance(outcome_notes, str) and outcome_notes.strip() else None

    return cleaned, None


def _delete_patient_uploads(patient):
    """Hasta silinirken ilişkili yüklenmiş görüntü dosyalarını da temizle."""
    filenames = []
    if patient.preop_analysis and patient.preop_analysis.image_filename:
        filenames.append(patient.preop_analysis.image_filename)
    for analysis in patient.postop_analyses.all():
        if analysis.image_filename:
            filenames.append(analysis.image_filename)

    for filename in filenames:
        path = UPLOAD_DIR / filename
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

patients_bp = Blueprint('patients', __name__, url_prefix='/api/patients')


def require_doctor_or_admin():
    """Decorator alternatifi: 401 don eger yetki yoksa"""
    if session.get('role') not in ('doctor', 'admin'):
        return jsonify({'error': 'Giris yapmalisiniz'}), 401
    return None


def require_admin():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin yetkisi gerekli'}), 403
    return None


@patients_bp.route('', methods=['POST'])
def create_patient():
    """
    Yeni hasta kaydi (doktor veya admin).
    Doktor: session'a created_patients listesine eklenir.
    """
    auth = require_doctor_or_admin()
    if auth:
        return auth
    
    try:
        data = request.get_json() or {}
        
        cleaned, error = _parse_patient_payload(data, partial=False)
        if error:
            return jsonify({'error': error}), 400
        
        patient = Patient(
            age=cleaned['age'],
            sex=cleaned['sex'],
            side=cleaned['side'],
            nail_brand=cleaned.get('nail_brand'),
            outcome=cleaned.get('outcome', 'pending'),
            outcome_notes=cleaned.get('outcome_notes'),
            created_by=session.get('name', 'Unknown'),
        )
        
        db.session.add(patient)
        db.session.commit()
        
        # Doktor session'ina kaydet (sonradan erisebilsin)
        if session.get('role') == 'doctor':
            created = session.get('created_patients', [])
            if patient.id not in created:
                created.append(patient.id)
                session['created_patients'] = created
                session.modified = True
        
        return jsonify({
            'success': True,
            'patient': patient.to_dict(detailed=True),
        }), 201
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@patients_bp.route('', methods=['GET'])
def list_patients():
    """
    Hasta listesi - SADECE ADMIN.
    Doktor listeyi goremez.
    """
    auth = require_admin()
    if auth:
        return auth
    
    try:
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 200)
        side_filter = request.args.get('side')
        sex_filter = request.args.get('sex')
        outcome_filter = request.args.get('outcome')
        nail_filter = request.args.get('nail_brand')
        
        query = Patient.query
        
        if side_filter:
            query = query.filter_by(side=side_filter)
        if sex_filter:
            query = query.filter_by(sex=sex_filter)
        if outcome_filter:
            query = query.filter_by(outcome=outcome_filter)
        if nail_filter:
            query = query.filter_by(nail_brand=nail_filter)
        
        query = query.order_by(Patient.created_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'success': True,
            'patients': [p.to_dict(detailed=True) for p in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@patients_bp.route('/<int:patient_id>', methods=['GET'])
def get_patient(patient_id):
    """
    Hasta detay.
    Doktor: sadece kendi olusturdugu hastayi (session check)
    Admin: tum hastalar
    """
    auth = require_doctor_or_admin()
    if auth:
        return auth
    
    # Doktor session check
    if session.get('role') == 'doctor':
        created = session.get('created_patients', [])
        if patient_id not in created:
            return jsonify({'error': 'Bu hastaya erisim yetkiniz yok'}), 403
    
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        data = patient.to_dict(detailed=True)
        data['preop_analysis'] = patient.preop_analysis.to_dict() if patient.preop_analysis else None
        data['postop_analyses'] = [p.to_dict() for p in patient.postop_analyses.all()]
        
        return jsonify({'success': True, 'patient': data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@patients_bp.route('/<int:patient_id>', methods=['PUT'])
def update_patient(patient_id):
    """
    Hasta guncelle - sonuc (outcome) eklemek icin.
    Doktor sadece kendi olusturdugu hastayi guncelleyebilir.
    """
    auth = require_doctor_or_admin()
    if auth:
        return auth
    
    if session.get('role') == 'doctor':
        created = session.get('created_patients', [])
        if patient_id not in created:
            return jsonify({'error': 'Bu hastayi guncelleyemezsiniz'}), 403
    
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.get_json() or {}
        
        allowed_fields = {'age', 'sex', 'side', 'nail_brand', 'outcome', 'outcome_notes'}
        cleaned, error = _parse_patient_payload(
            {k: v for k, v in data.items() if k in allowed_fields},
            partial=True,
        )
        if error:
            return jsonify({'error': error}), 400

        for field, value in cleaned.items():
            setattr(patient, field, value)
        
        db.session.commit()
        return jsonify({'success': True, 'patient': patient.to_dict(detailed=True)})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@patients_bp.route('/<int:patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    """Hastayi sil - SADECE ADMIN."""
    auth = require_admin()
    if auth:
        return auth
    
    try:
        patient = Patient.query.get_or_404(patient_id)
        _delete_patient_uploads(patient)
        db.session.delete(patient)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Hasta #{patient_id} silindi'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@patients_bp.route('/stats', methods=['GET'])
def patient_stats():
    """Genel istatistikler - SADECE ADMIN."""
    auth = require_admin()
    if auth:
        return auth
    
    try:
        from sqlalchemy import func
        
        total = Patient.query.count()
        male = Patient.query.filter_by(sex='M').count()
        female = Patient.query.filter_by(sex='F').count()
        right = Patient.query.filter_by(side='right').count()
        left = Patient.query.filter_by(side='left').count()
        
        # Outcome dagilimi
        union = Patient.query.filter_by(outcome='union').count()
        failure = Patient.query.filter_by(outcome='failure').count()
        pending = Patient.query.filter(
            (Patient.outcome == 'pending') | (Patient.outcome == None)
        ).count()
        
        # Yas
        age_stats = db.session.query(
            func.avg(Patient.age),
            func.min(Patient.age),
            func.max(Patient.age),
        ).first()
        
        # Civi markasi dagilimi
        nail_dist = db.session.query(
            Patient.nail_brand, func.count(Patient.id)
        ).group_by(Patient.nail_brand).all()
        
        return jsonify({
            'success': True,
            'total': total,
            'sex': {'male': male, 'female': female},
            'side': {'right': right, 'left': left},
            'outcome': {
                'union': union,
                'failure': failure,
                'pending': pending,
                'failure_rate': failure / max(total, 1),
            },
            'age': {
                'mean': float(age_stats[0]) if age_stats[0] else None,
                'min': age_stats[1],
                'max': age_stats[2],
            },
            'nail_brands': [
                {'brand': brand or 'Belirsiz', 'count': count}
                for brand, count in nail_dist
            ],
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@patients_bp.route('/export-csv', methods=['GET'])
def export_csv():
    """Tum verileri CSV olarak indir - SADECE ADMIN."""
    auth = require_admin()
    if auth:
        return auth
    
    try:
        import csv
        import io
        from flask import Response
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            'patient_id', 'age', 'sex', 'side', 'nail_brand', 'outcome',
            'preop_ao_class', 'preop_confidence',
            'postop_ap_tad', 'postop_ap_nsa', 'postop_ap_cleveland', 'postop_ap_parker_ap',
            'postop_ap_risk_score', 'postop_ap_risk_category',
            'postop_lat_tad', 'has_lat',
            'created_by', 'created_at'
        ])
        
        for p in Patient.query.order_by(Patient.id).all():
            preop = p.preop_analysis
            postop_ap_list = p.postop_analyses.filter_by(view_type='AP').all()
            postop_lat_list = p.postop_analyses.filter_by(view_type='LAT').all()
            
            ap = postop_ap_list[0] if postop_ap_list else None
            lat = postop_lat_list[0] if postop_lat_list else None
            
            writer.writerow([
                p.id, p.age, p.sex, p.side, p.nail_brand or '', p.outcome or 'pending',
                (preop.final_class if preop else ''),
                (preop.ai_confidence if preop else ''),
                (ap.tad_ap_mm if ap else ''),
                (ap.nsa_deg if ap else ''),
                (ap.cleveland_zone if ap else ''),
                (ap.parker_ap_ratio if ap else ''),
                (ap.risk_score if ap else ''),
                (ap.risk_category if ap else ''),
                (lat.tad_lat_mm if lat else ''),
                ('yes' if lat else 'no'),
                p.created_by or '',
                p.created_at.isoformat() if p.created_at else '',
            ])
        
        csv_data = output.getvalue()
        output.close()
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=pfn_data.csv'}
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

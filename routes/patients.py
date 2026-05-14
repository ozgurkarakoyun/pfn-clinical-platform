"""
Hasta CRUD endpoint'leri
"""
from datetime import datetime, date
from flask import Blueprint, request, jsonify, current_app
from models import db, Patient, Surgery

patients_bp = Blueprint('patients', __name__, url_prefix='/api/patients')


def parse_date(date_str):
    """ISO string'i date'e cevir, None ise None don"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


@patients_bp.route('', methods=['POST'])
def create_patient():
    """Yeni hasta kaydi"""
    try:
        data = request.get_json() or {}
        
        # Zorunlu alanlar
        if not data.get('age') or not data.get('sex') or not data.get('side'):
            return jsonify({'error': 'Yas, cinsiyet ve taraf zorunlu'}), 400
        
        if data['sex'] not in ('M', 'F'):
            return jsonify({'error': 'Cinsiyet M veya F olmali'}), 400
        if data['side'] not in ('right', 'left'):
            return jsonify({'error': 'Taraf right veya left olmali'}), 400
        
        # Tarih farkindan delay_days hesapla
        fracture_date = parse_date(data.get('fracture_date'))
        surgery_date = parse_date(data.get('surgery_date'))
        delay_days = None
        if fracture_date and surgery_date:
            delay_days = (surgery_date - fracture_date).days
        
        patient = Patient(
            hospital_code=data.get('hospital_code'),
            age=int(data['age']),
            sex=data['sex'],
            side=data['side'],
            weight_kg=data.get('weight_kg'),
            height_cm=data.get('height_cm'),
            fracture_date=fracture_date,
            surgery_date=surgery_date,
            delay_days=delay_days,
            asa_score=data.get('asa_score'),
            comorbidities=data.get('comorbidities', []),
            anticoagulant=data.get('anticoagulant', False),
            pre_fracture_mobility=data.get('pre_fracture_mobility'),
            notes=data.get('notes'),
        )
        
        db.session.add(patient)
        db.session.flush()  # ID'yi al
        
        # Cerrahi bilgileri varsa kaydet
        surgery_data = data.get('surgery')
        if surgery_data:
            surgery = Surgery(
                patient_id=patient.id,
                nail_brand=surgery_data.get('nail_brand'),
                nail_length_mm=surgery_data.get('nail_length_mm'),
                nail_angle_deg=surgery_data.get('nail_angle_deg'),
                nail_diameter_mm=surgery_data.get('nail_diameter_mm'),
                lag_screw_type=surgery_data.get('lag_screw_type'),
                locking_mode=surgery_data.get('locking_mode'),
                operation_duration_min=surgery_data.get('operation_duration_min'),
                blood_loss_ml=surgery_data.get('blood_loss_ml'),
                surgeon_experience=surgery_data.get('surgeon_experience'),
                notes=surgery_data.get('notes'),
            )
            db.session.add(surgery)
        
        db.session.commit()
        
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
    """Hasta listesi (sayfalandirilmis)"""
    try:
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 20)), 100)
        search = request.args.get('search', '').strip()
        side_filter = request.args.get('side')
        sex_filter = request.args.get('sex')
        
        query = Patient.query
        
        if side_filter:
            query = query.filter_by(side=side_filter)
        if sex_filter:
            query = query.filter_by(sex=sex_filter)
        if search:
            query = query.filter(Patient.hospital_code.ilike(f'%{search}%'))
        
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
    """Hasta detayi (analiz ve takip dahil)"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        data = patient.to_dict(detailed=True)
        data['surgery'] = patient.surgery.to_dict() if patient.surgery else None
        data['preop_analysis'] = patient.preop_analysis.to_dict() if patient.preop_analysis else None
        data['postop_analyses'] = [p.to_dict() for p in patient.postop_analyses.all()]
        data['followups'] = [f.to_dict() for f in patient.followups.all()]
        
        return jsonify({'success': True, 'patient': data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@patients_bp.route('/<int:patient_id>', methods=['PUT'])
def update_patient(patient_id):
    """Hasta bilgilerini guncelle"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.get_json() or {}
        
        for field in ['hospital_code', 'age', 'sex', 'side', 'weight_kg', 'height_cm',
                      'asa_score', 'comorbidities', 'anticoagulant',
                      'pre_fracture_mobility', 'notes']:
            if field in data:
                setattr(patient, field, data[field])
        
        if 'fracture_date' in data:
            patient.fracture_date = parse_date(data['fracture_date'])
        if 'surgery_date' in data:
            patient.surgery_date = parse_date(data['surgery_date'])
        
        # delay_days yeniden hesapla
        if patient.fracture_date and patient.surgery_date:
            patient.delay_days = (patient.surgery_date - patient.fracture_date).days
        
        db.session.commit()
        return jsonify({'success': True, 'patient': patient.to_dict(detailed=True)})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@patients_bp.route('/<int:patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    """Hastayi sil (tum iliskili veriler cascade)"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        db.session.delete(patient)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Hasta #{patient_id} silindi'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@patients_bp.route('/<int:patient_id>/surgery', methods=['POST', 'PUT'])
def upsert_surgery(patient_id):
    """Cerrahi bilgileri ekle veya guncelle"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.get_json() or {}
        
        if patient.surgery:
            surgery = patient.surgery
            for field in ['nail_brand', 'nail_length_mm', 'nail_angle_deg',
                          'nail_diameter_mm', 'lag_screw_type', 'locking_mode',
                          'operation_duration_min', 'blood_loss_ml',
                          'surgeon_experience', 'notes']:
                if field in data:
                    setattr(surgery, field, data[field])
        else:
            surgery = Surgery(patient_id=patient_id, **{k: v for k, v in data.items() 
                              if k in ['nail_brand', 'nail_length_mm', 'nail_angle_deg',
                                       'nail_diameter_mm', 'lag_screw_type', 'locking_mode',
                                       'operation_duration_min', 'blood_loss_ml',
                                       'surgeon_experience', 'notes']})
            db.session.add(surgery)
        
        db.session.commit()
        return jsonify({'success': True, 'surgery': surgery.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@patients_bp.route('/stats', methods=['GET'])
def patient_stats():
    """Genel istatistikler"""
    try:
        total = Patient.query.count()
        male = Patient.query.filter_by(sex='M').count()
        female = Patient.query.filter_by(sex='F').count()
        right = Patient.query.filter_by(side='right').count()
        left = Patient.query.filter_by(side='left').count()
        
        # Yas dagilimi
        from sqlalchemy import func
        age_stats = db.session.query(
            func.avg(Patient.age),
            func.min(Patient.age),
            func.max(Patient.age),
        ).first()
        
        return jsonify({
            'success': True,
            'total': total,
            'sex': {'male': male, 'female': female},
            'side': {'right': right, 'left': left},
            'age': {
                'mean': float(age_stats[0]) if age_stats[0] else None,
                'min': age_stats[1],
                'max': age_stats[2],
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

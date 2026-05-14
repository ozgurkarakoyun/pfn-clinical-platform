"""
Takip (Followup) endpoint'leri
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from models import db, Patient, Followup

followup_bp = Blueprint('followup', __name__, url_prefix='/api/followup')


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


@followup_bp.route('/<int:patient_id>', methods=['POST'])
def create_followup(patient_id):
    """Yeni takip kaydi olustur"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        data = request.get_json() or {}
        
        followup_date = parse_date(data.get('followup_date'))
        if not followup_date:
            return jsonify({'error': 'Takip tarihi zorunlu'}), 400
        
        # weeks_post_op otomatik hesapla
        weeks_post_op = data.get('weeks_post_op')
        if weeks_post_op is None and patient.surgery_date:
            days = (followup_date - patient.surgery_date).days
            weeks_post_op = max(0, days // 7)
        
        followup = Followup(
            patient_id=patient_id,
            followup_date=followup_date,
            weeks_post_op=weeks_post_op,
            cut_out=data.get('cut_out', False),
            screw_migration=data.get('screw_migration', False),
            union_status=data.get('union_status'),
            complications=data.get('complications', []),
            vas_score=data.get('vas_score'),
            harris_hip_score=data.get('harris_hip_score'),
            mortality=data.get('mortality', False),
            mortality_date=parse_date(data.get('mortality_date')),
            notes=data.get('notes'),
        )
        db.session.add(followup)
        db.session.commit()
        
        return jsonify({'success': True, 'followup': followup.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@followup_bp.route('/<int:patient_id>', methods=['GET'])
def list_followups(patient_id):
    """Hastanin tum takiplerini dondur"""
    patient = Patient.query.get_or_404(patient_id)
    followups = patient.followups.order_by(Followup.followup_date.desc()).all()
    return jsonify({
        'success': True,
        'followups': [f.to_dict() for f in followups]
    })


@followup_bp.route('/<int:followup_id>/update', methods=['PUT'])
def update_followup(followup_id):
    """Takip guncelle"""
    try:
        followup = Followup.query.get_or_404(followup_id)
        data = request.get_json() or {}
        
        for field in ['cut_out', 'screw_migration', 'union_status', 'complications',
                      'vas_score', 'harris_hip_score', 'mortality', 'notes']:
            if field in data:
                setattr(followup, field, data[field])
        
        if 'followup_date' in data:
            followup.followup_date = parse_date(data['followup_date'])
        if 'mortality_date' in data:
            followup.mortality_date = parse_date(data['mortality_date'])
        
        db.session.commit()
        return jsonify({'success': True, 'followup': followup.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@followup_bp.route('/<int:followup_id>', methods=['DELETE'])
def delete_followup(followup_id):
    try:
        followup = Followup.query.get_or_404(followup_id)
        db.session.delete(followup)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@followup_bp.route('/stats/outcomes', methods=['GET'])
def outcome_stats():
    """Genel outcome istatistikleri"""
    try:
        total = Followup.query.count()
        cut_outs = Followup.query.filter_by(cut_out=True).count()
        migrations = Followup.query.filter_by(screw_migration=True).count()
        mortalities = Followup.query.filter_by(mortality=True).count()
        
        return jsonify({
            'success': True,
            'total_followups': total,
            'cut_out_count': cut_outs,
            'screw_migration_count': migrations,
            'mortality_count': mortalities,
            'failure_rate': cut_outs / max(total, 1),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

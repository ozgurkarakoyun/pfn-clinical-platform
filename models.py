"""
Database Modelleri
- Patient: Hasta demografik bilgileri
- Surgery: Cerrahi detaylar
- PreopAnalysis: AO siniflama AI sonucu
- PostopAnalysis: PFN keypoint AI sonucu (AP + LAT)
- Followup: Takip kayitlari
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Patient(db.Model):
    """Hasta demografik ve klinik bilgileri"""
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Anonim tanimlayici (TC kimlik degil)
    hospital_code = db.Column(db.String(50), nullable=True)
    
    # Demografik
    age = db.Column(db.Integer, nullable=False)
    sex = db.Column(db.String(1), nullable=False)  # M / F
    weight_kg = db.Column(db.Float, nullable=True)
    height_cm = db.Column(db.Float, nullable=True)
    
    # Kirik
    side = db.Column(db.String(5), nullable=False)  # right / left
    fracture_date = db.Column(db.Date, nullable=True)
    surgery_date = db.Column(db.Date, nullable=True)
    delay_days = db.Column(db.Integer, nullable=True)
    
    # Klinik
    asa_score = db.Column(db.Integer, nullable=True)  # 1-5
    comorbidities = db.Column(db.JSON, default=list)  # ["HT", "DM", "KOAH"...]
    anticoagulant = db.Column(db.Boolean, default=False)
    pre_fracture_mobility = db.Column(db.String(50), nullable=True)
    
    # Meta
    created_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    # Iliskiler
    surgery = db.relationship('Surgery', backref='patient', uselist=False, cascade='all, delete-orphan')
    preop_analysis = db.relationship('PreopAnalysis', backref='patient', uselist=False, cascade='all, delete-orphan')
    postop_analyses = db.relationship('PostopAnalysis', backref='patient', lazy='dynamic', cascade='all, delete-orphan')
    followups = db.relationship('Followup', backref='patient', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self, detailed=False):
        data = {
            'id': self.id,
            'hospital_code': self.hospital_code,
            'age': self.age,
            'sex': self.sex,
            'side': self.side,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if detailed:
            data.update({
                'weight_kg': self.weight_kg,
                'height_cm': self.height_cm,
                'fracture_date': self.fracture_date.isoformat() if self.fracture_date else None,
                'surgery_date': self.surgery_date.isoformat() if self.surgery_date else None,
                'delay_days': self.delay_days,
                'asa_score': self.asa_score,
                'comorbidities': self.comorbidities or [],
                'anticoagulant': self.anticoagulant,
                'pre_fracture_mobility': self.pre_fracture_mobility,
                'notes': self.notes,
                'has_surgery_info': self.surgery is not None,
                'has_preop': self.preop_analysis is not None,
                'postop_count': self.postop_analyses.count(),
                'followup_count': self.followups.count(),
            })
        return data


class Surgery(db.Model):
    """Cerrahi detaylar"""
    __tablename__ = 'surgeries'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False, unique=True)
    
    # Implant
    nail_brand = db.Column(db.String(50), nullable=True)  # PFNA, Gamma 3, TFN, InterTAN, vb.
    nail_length_mm = db.Column(db.Integer, nullable=True)
    nail_angle_deg = db.Column(db.Integer, nullable=True)  # 125, 130, 135
    nail_diameter_mm = db.Column(db.Float, nullable=True)
    
    lag_screw_type = db.Column(db.String(30), nullable=True)  # helical_blade / threaded_screw
    locking_mode = db.Column(db.String(20), nullable=True)  # static / dynamic
    
    # Cerrahi
    operation_duration_min = db.Column(db.Integer, nullable=True)
    blood_loss_ml = db.Column(db.Integer, nullable=True)
    surgeon_experience = db.Column(db.String(20), nullable=True)  # junior / mid / senior
    
    # Meta
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'nail_brand': self.nail_brand,
            'nail_length_mm': self.nail_length_mm,
            'nail_angle_deg': self.nail_angle_deg,
            'nail_diameter_mm': self.nail_diameter_mm,
            'lag_screw_type': self.lag_screw_type,
            'locking_mode': self.locking_mode,
            'operation_duration_min': self.operation_duration_min,
            'blood_loss_ml': self.blood_loss_ml,
            'surgeon_experience': self.surgeon_experience,
            'notes': self.notes,
        }


class PreopAnalysis(db.Model):
    """Preoperatif AO siniflama AI sonucu"""
    __tablename__ = 'preop_analyses'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False, unique=True)
    
    # Goruntu
    image_filename = db.Column(db.String(255), nullable=False)
    image_width = db.Column(db.Integer, nullable=True)
    image_height = db.Column(db.Integer, nullable=True)
    
    # AI sonucu
    ai_class = db.Column(db.String(20), nullable=True)  # 31-A1, 31-A2, 31-A3, 31-B, normal
    ai_confidence = db.Column(db.Float, nullable=True)
    ai_bbox = db.Column(db.JSON, nullable=True)  # [x1, y1, x2, y2]
    ai_all_predictions = db.Column(db.JSON, nullable=True)  # Tum tahminler
    
    # Manuel duzeltme
    manual_class = db.Column(db.String(20), nullable=True)
    manual_corrected = db.Column(db.Boolean, default=False)
    
    # Klinik notlar
    fracture_displacement = db.Column(db.String(20), nullable=True)
    lateral_wall_integrity = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Meta
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def final_class(self):
        """Manuel duzeltilmisse onu, yoksa AI tahminini dondur"""
        return self.manual_class if self.manual_corrected else self.ai_class
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'image_filename': self.image_filename,
            'image_url': f'/static/uploads/{self.image_filename}',
            'ai_class': self.ai_class,
            'ai_confidence': self.ai_confidence,
            'ai_bbox': self.ai_bbox,
            'ai_all_predictions': self.ai_all_predictions,
            'manual_class': self.manual_class,
            'manual_corrected': self.manual_corrected,
            'final_class': self.final_class,
            'fracture_displacement': self.fracture_displacement,
            'lateral_wall_integrity': self.lateral_wall_integrity,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PostopAnalysis(db.Model):
    """Postoperatif PFN keypoint AI analizi (AP veya LAT)"""
    __tablename__ = 'postop_analyses'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    # Goruntu tipi
    view_type = db.Column(db.String(5), nullable=False)  # AP veya LAT
    image_filename = db.Column(db.String(255), nullable=False)
    image_width = db.Column(db.Integer, nullable=True)
    image_height = db.Column(db.Integer, nullable=True)
    
    # AI tespit
    detected_side = db.Column(db.String(5), nullable=True)  # right / left (auto-detect)
    detection_confidence = db.Column(db.Float, nullable=True)
    
    # Keypointler
    keypoints = db.Column(db.JSON, nullable=True)  # {name: [x, y], ...}
    keypoints_manual_corrected = db.Column(db.Boolean, default=False)
    
    # APEX (manuel veya otomatik)
    apex_point = db.Column(db.JSON, nullable=True)  # [x, y]
    apex_method = db.Column(db.String(30), nullable=True)  # anatomic_neck_axis / manual
    
    # Kalibrasyon
    pixel_spacing_mm = db.Column(db.Float, nullable=True)
    calibration_method = db.Column(db.String(30), nullable=True)  # dicom / manual / visual
    d_true_mm = db.Column(db.Float, nullable=True)
    
    # Hesaplanan parametreler
    tad_ap_mm = db.Column(db.Float, nullable=True)
    tad_lat_mm = db.Column(db.Float, nullable=True)  # Sadece LAT goruntude
    nsa_deg = db.Column(db.Float, nullable=True)
    cleveland_zone = db.Column(db.String(30), nullable=True)
    parker_ap_ratio = db.Column(db.Float, nullable=True)
    parker_ml_ratio = db.Column(db.Float, nullable=True)
    femur_head_diameter_mm = db.Column(db.Float, nullable=True)
    
    # Risk degerlendirmesi
    risk_score = db.Column(db.Integer, nullable=True)
    risk_category = db.Column(db.String(20), nullable=True)
    risk_factors = db.Column(db.JSON, nullable=True)
    
    # DICOM metadata (varsa)
    dicom_metadata = db.Column(db.JSON, nullable=True)
    
    # Meta
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'view_type': self.view_type,
            'image_filename': self.image_filename,
            'image_url': f'/static/uploads/{self.image_filename}',
            'image_width': self.image_width,
            'image_height': self.image_height,
            'detected_side': self.detected_side,
            'detection_confidence': self.detection_confidence,
            'keypoints': self.keypoints,
            'keypoints_manual_corrected': self.keypoints_manual_corrected,
            'apex_point': self.apex_point,
            'apex_method': self.apex_method,
            'pixel_spacing_mm': self.pixel_spacing_mm,
            'calibration_method': self.calibration_method,
            'd_true_mm': self.d_true_mm,
            'tad_ap_mm': self.tad_ap_mm,
            'tad_lat_mm': self.tad_lat_mm,
            'nsa_deg': self.nsa_deg,
            'cleveland_zone': self.cleveland_zone,
            'parker_ap_ratio': self.parker_ap_ratio,
            'parker_ml_ratio': self.parker_ml_ratio,
            'femur_head_diameter_mm': self.femur_head_diameter_mm,
            'risk_score': self.risk_score,
            'risk_category': self.risk_category,
            'risk_factors': self.risk_factors,
            'dicom_metadata': self.dicom_metadata,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Followup(db.Model):
    """Postop takip kayitlari"""
    __tablename__ = 'followups'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    # Takip bilgisi
    followup_date = db.Column(db.Date, nullable=False)
    weeks_post_op = db.Column(db.Integer, nullable=True)
    
    # Outcome
    cut_out = db.Column(db.Boolean, default=False)
    screw_migration = db.Column(db.Boolean, default=False)
    union_status = db.Column(db.String(20), nullable=True)  # united / delayed / nonunion
    complications = db.Column(db.JSON, default=list)
    
    # Klinik skor
    vas_score = db.Column(db.Integer, nullable=True)  # 0-10
    harris_hip_score = db.Column(db.Integer, nullable=True)  # 0-100
    
    # Mortality
    mortality = db.Column(db.Boolean, default=False)
    mortality_date = db.Column(db.Date, nullable=True)
    
    # Takip grafisi (opsiyonel)
    image_filename = db.Column(db.String(255), nullable=True)
    
    # Meta
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'followup_date': self.followup_date.isoformat() if self.followup_date else None,
            'weeks_post_op': self.weeks_post_op,
            'cut_out': self.cut_out,
            'screw_migration': self.screw_migration,
            'union_status': self.union_status,
            'complications': self.complications or [],
            'vas_score': self.vas_score,
            'harris_hip_score': self.harris_hip_score,
            'mortality': self.mortality,
            'mortality_date': self.mortality_date.isoformat() if self.mortality_date else None,
            'image_filename': self.image_filename,
            'image_url': f'/static/uploads/{self.image_filename}' if self.image_filename else None,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

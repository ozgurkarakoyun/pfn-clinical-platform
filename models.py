"""
Sadelestirilmis Database Modelleri.
- Patient: yas, cinsiyet, taraf, civi markasi, outcome
- PreopAnalysis: AO siniflama
- PostopAnalysis: PFN keypoint (AP veya LAT)
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Patient(db.Model):
    """Hasta - sade veri seti"""
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Demografik
    age = db.Column(db.Integer, nullable=False)
    sex = db.Column(db.String(1), nullable=False)  # M / F
    side = db.Column(db.String(5), nullable=False)  # right / left
    
    # Cerrahi (sadece civi markasi)
    nail_brand = db.Column(db.String(50), nullable=True)
    
    # Sonuc (outcome)
    outcome = db.Column(db.String(20), nullable=True)  # union / failure / pending
    outcome_notes = db.Column(db.Text, nullable=True)
    
    # Meta
    created_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Iliskiler
    preop_analysis = db.relationship('PreopAnalysis', backref='patient', uselist=False, cascade='all, delete-orphan')
    postop_analyses = db.relationship('PostopAnalysis', backref='patient', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self, detailed=False):
        data = {
            'id': self.id,
            'age': self.age,
            'sex': self.sex,
            'side': self.side,
            'nail_brand': self.nail_brand,
            'outcome': self.outcome or 'pending',
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if detailed:
            data.update({
                'outcome_notes': self.outcome_notes,
                'has_preop': self.preop_analysis is not None,
                'postop_count': self.postop_analyses.count(),
                'has_postop_ap': self.postop_analyses.filter_by(view_type='AP').count() > 0,
                'has_postop_lat': self.postop_analyses.filter_by(view_type='LAT').count() > 0,
            })
        return data


class PreopAnalysis(db.Model):
    """Preoperatif AO Siniflama"""
    __tablename__ = 'preop_analyses'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False, unique=True)
    
    image_filename = db.Column(db.String(255), nullable=True)  # Manuel only kayit icin null olabilir
    image_url = db.Column(db.Text, nullable=True)  # Cloudinary URL veya /static/uploads/X.jpg
    storage_id = db.Column(db.String(500), nullable=True)  # Silme icin
    storage_type = db.Column(db.String(20), nullable=True)  # 'cloudinary' veya 'local'
    image_width = db.Column(db.Integer, nullable=True)
    image_height = db.Column(db.Integer, nullable=True)
    
    ai_class = db.Column(db.String(20), nullable=True)
    ai_confidence = db.Column(db.Float, nullable=True)
    ai_bbox = db.Column(db.JSON, nullable=True)
    ai_all_predictions = db.Column(db.JSON, nullable=True)
    
    manual_class = db.Column(db.String(20), nullable=True)
    manual_corrected = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def final_class(self):
        return self.manual_class if self.manual_corrected else self.ai_class
    
    @property
    def has_image(self):
        return bool(self.image_filename or self.image_url)
    
    @property
    def display_url(self):
        """Frontend icin URL - Cloudinary veya lokal"""
        if self.image_url:
            return self.image_url
        if self.image_filename:
            return f'/static/uploads/{self.image_filename}'
        return None
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'image_url': self.display_url,
            'has_image': self.has_image,
            'storage_type': self.storage_type,
            'ai_class': self.ai_class,
            'ai_confidence': self.ai_confidence,
            'ai_bbox': self.ai_bbox,
            'ai_all_predictions': self.ai_all_predictions,
            'manual_class': self.manual_class,
            'manual_corrected': self.manual_corrected,
            'final_class': self.final_class,
        }


class PostopAnalysis(db.Model):
    """Postoperatif PFN Keypoint (AP veya LAT)"""
    __tablename__ = 'postop_analyses'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    view_type = db.Column(db.String(5), nullable=False)  # AP / LAT
    image_filename = db.Column(db.String(255), nullable=True)  # Lokal fallback
    image_url = db.Column(db.Text, nullable=True)  # Cloudinary URL veya lokal path
    storage_id = db.Column(db.String(500), nullable=True)
    storage_type = db.Column(db.String(20), nullable=True)
    image_width = db.Column(db.Integer, nullable=True)
    image_height = db.Column(db.Integer, nullable=True)
    
    detected_side = db.Column(db.String(5), nullable=True)
    detection_confidence = db.Column(db.Float, nullable=True)
    
    keypoints = db.Column(db.JSON, nullable=True)
    keypoints_manual_corrected = db.Column(db.Boolean, default=False)
    
    apex_point = db.Column(db.JSON, nullable=True)
    apex_method = db.Column(db.String(30), nullable=True)
    
    pixel_spacing_mm = db.Column(db.Float, nullable=True)
    calibration_method = db.Column(db.String(30), nullable=True)
    d_true_mm = db.Column(db.Float, nullable=True)
    
    tad_ap_mm = db.Column(db.Float, nullable=True)
    tad_lat_mm = db.Column(db.Float, nullable=True)
    nsa_deg = db.Column(db.Float, nullable=True)
    cleveland_zone = db.Column(db.String(30), nullable=True)
    parker_ap_ratio = db.Column(db.Float, nullable=True)
    parker_ml_ratio = db.Column(db.Float, nullable=True)
    femur_head_diameter_mm = db.Column(db.Float, nullable=True)
    
    risk_score = db.Column(db.Integer, nullable=True)
    risk_category = db.Column(db.String(20), nullable=True)
    risk_factors = db.Column(db.JSON, nullable=True)
    
    dicom_metadata = db.Column(db.JSON, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def display_url(self):
        """Frontend icin URL"""
        if self.image_url:
            return self.image_url
        if self.image_filename:
            return f'/static/uploads/{self.image_filename}'
        return None
    
    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'view_type': self.view_type,
            'image_url': self.display_url,
            'storage_type': self.storage_type,
            'image_width': self.image_width,
            'image_height': self.image_height,
            'detected_side': self.detected_side,
            'detection_confidence': self.detection_confidence,
            'keypoints': self.keypoints,
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
        }

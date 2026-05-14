"""
PFN Klinik Arastirma Platformu v2 (Sadelestirilmis)
- Doktor: hasta kaydeder (gecmise erisemez)
- Admin: tum hastalari gorur + istatistik
"""
import os
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

load_dotenv()

app = Flask(__name__)
CORS(app)

# Konfigurasyon
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# Database
database_url = os.environ.get('DATABASE_URL', 'sqlite:///pfn_local.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload
app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Yetkilendirme kimlikleri (environment variable'dan alir)
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
DOCTOR_CODE = os.environ.get('DOCTOR_CODE', 'doktor2025')

# Database
from models import db
db.init_app(app)
migrate = Migrate(app, db)

# Decorators
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def doctor_or_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ('doctor', 'admin'):
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_api_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin yetkisi gerekli'}), 403
        return f(*args, **kwargs)
    return decorated


def doctor_or_admin_api_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ('doctor', 'admin'):
            return jsonify({'error': 'Giris yapmalisiniz'}), 401
        return f(*args, **kwargs)
    return decorated


# Routes - kayitlar
from routes.patients import patients_bp
from routes.preop import preop_bp
from routes.postop import postop_bp

app.register_blueprint(patients_bp)
app.register_blueprint(preop_bp)
app.register_blueprint(postop_bp)


# ============= LOGIN =============
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Giris sayfasi - admin veya doktor"""
    if request.method == 'POST':
        data = request.get_json() or request.form
        login_type = data.get('login_type')
        
        if login_type == 'admin':
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                session.permanent = True
                session['role'] = 'admin'
                session['name'] = 'Admin'
                return jsonify({'success': True, 'redirect': '/admin'})
            return jsonify({'success': False, 'error': 'Yanlis kullanici/sifre'}), 401
        
        elif login_type == 'doctor':
            code = data.get('code', '').strip()
            doctor_name = data.get('doctor_name', '').strip() or 'Doktor'
            
            if code == DOCTOR_CODE:
                session.permanent = True
                session['role'] = 'doctor'
                session['name'] = doctor_name
                return jsonify({'success': True, 'redirect': '/'})
            return jsonify({'success': False, 'error': 'Yanlis erisim kodu'}), 401
        
        return jsonify({'success': False, 'error': 'Gecersiz istek'}), 400
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


# ============= DOKTOR SAYFALARI =============
@app.route('/')
@doctor_or_admin_required
def index():
    """
    Doktor: sadece yeni hasta formu
    Admin: hasta listesine yonlendir
    """
    if session.get('role') == 'admin':
        return redirect(url_for('admin_patient_list'))
    return render_template('doctor_new_patient.html', user_name=session.get('name'))


@app.route('/patient/<int:patient_id>')
@doctor_or_admin_required
def patient_detail(patient_id):
    """
    Hasta detay - grafi yukleme sayfasi
    Doktor: sadece kendi olusturdugu hastayi (session'da takip)
    Admin: tum hastalar
    """
    if session.get('role') == 'doctor':
        # Doktor sadece kendi olusturdugu hastalari gorebilir
        created_patients = session.get('created_patients', [])
        if patient_id not in created_patients:
            return redirect(url_for('index'))
    
    return render_template('patient_detail.html', 
                          patient_id=patient_id,
                          user_role=session.get('role'),
                          user_name=session.get('name'))


# ============= ADMIN SAYFALARI =============
@app.route('/admin')
@admin_required
def admin_patient_list():
    """Admin hasta listesi"""
    return render_template('admin_patient_list.html', user_name=session.get('name'))


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin istatistik dashboard"""
    return render_template('admin_dashboard.html', user_name=session.get('name'))


# ============= API =============
@app.route('/api/whoami')
def whoami():
    """Mevcut kullanicinin rolu"""
    return jsonify({
        'role': session.get('role'),
        'name': session.get('name'),
        'logged_in': session.get('role') is not None,
    })


@app.route('/health')
def health():
    """Saglik kontrolu"""
    try:
        db.session.execute(db.text('SELECT 1'))
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    return jsonify({
        'status': 'ok',
        'database': db_status,
        'timestamp': datetime.utcnow().isoformat()
    })


# ============= CLI =============
@app.cli.command('init-db')
def init_db_command():
    """Veritabani tablolarini olustur"""
    with app.app_context():
        db.create_all()
    print('Database tablolari olusturuldu.')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

"""
PFN Klinik Arastirma Platformu v2
- Hasta kaydı
- AO Sınıflama AI (preop)
- PFN Keypoint AI (postop AP + LAT)
- Takip ve veritabanı
"""
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# .env dosyasini yukle (lokal gelistirme icin)
load_dotenv()

# Flask uygulamasi
app = Flask(__name__)
CORS(app)

# Konfigurasyon
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

# Database URL - Railway PostgreSQL veya lokal
database_url = os.environ.get('DATABASE_URL', 'sqlite:///pfn_local.db')
# Railway eski 'postgres://' formatini SQLAlchemy 'postgresql://' icin duzelt
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Max upload boyutu
app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024  # 30 MB

# Klasorler
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Database ve migrate
from models import db
db.init_app(app)
migrate = Migrate(app, db)

# Routes
from routes.patients import patients_bp
from routes.preop import preop_bp
from routes.postop import postop_bp
from routes.followup import followup_bp

app.register_blueprint(patients_bp)
app.register_blueprint(preop_bp)
app.register_blueprint(postop_bp)
app.register_blueprint(followup_bp)


# Ana sayfalar
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/patient/<int:patient_id>')
def patient_detail(patient_id):
    return render_template('patient_detail.html', patient_id=patient_id)


@app.route('/new-patient')
def new_patient_form():
    return render_template('new_patient.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/health')
def health():
    """Railway saglik kontrolu"""
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


# CLI komutu - database init
@app.cli.command('init-db')
def init_db_command():
    """Veritabani tablolarini olustur"""
    with app.app_context():
        db.create_all()
    print('Database tablolari olusturuldu.')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

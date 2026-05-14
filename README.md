# PFN Klinik Arastirma Platformu v2

Pertrochanteric femur fracture (PFN) icin AI tabanli klinik arastirma platformu.

## Sade Veri Modeli

**Toplanan veriler:**
- Yas, cinsiyet, kirik tarafi
- Civi markasi (varsa)
- Outcome (kaynama / failure / belirsiz)
- Preop grafi -> AO siniflama
- Postop AP grafi (zorunlu)
- Postop LAT grafi (varsa - toplam TAD icin)

## Kullanici Rolleri

### Doktor
- Erisim kodu ile giris
- Sadece **kendi olusturdugu** hastalari gorebilir
- Hasta listesi ve dashboard'a erisemez
- Hasta kaydeder, grafileri yukler, outcome guncelleyebilir

### Admin
- Kullanici/sifre ile giris
- **Tum hastalari** gorur
- Istatistik dashboard
- CSV export
- Hasta silebilir

## RAILWAY DEPLOY

### 1. GitHub'a Yukle
ZIP'i acin, GitHub repo'sunda dosyalar olarak yukleyin.

### 2. Railway Proje Olustur
- Railway -> New Project -> Deploy from GitHub repo

### 3. PostgreSQL Ekle
- + New -> Database -> PostgreSQL

### 4. Environment Variables

| Variable | Aciklama | Ornek |
|----------|----------|-------|
| `SECRET_KEY` | Flask session key (gerekli) | `openssl rand -hex 32` |
| `ADMIN_USERNAME` | Admin kullanici adi | `admin` |
| `ADMIN_PASSWORD` | Admin sifresi | Guclu sifre |
| `DOCTOR_CODE` | Doktor erisim kodu | `pfn2025` |
| `DATABASE_URL` | (PostgreSQL ile otomatik gelir) | - |

⚠️ Default degerler **kesinlikle production'da degistirilmeli**:
- ADMIN_PASSWORD default `admin123` (degistir!)
- DOCTOR_CODE default `doktor2025` (degistir!)

### 5. Modelleri Yukle
Volume mount ile `/app/models_files/` icine:
- `best.pt` - PFN keypoint
- `femur_model.pt` - AO classification

### 6. Test
- `/health` - DB baglantisi
- `/login` - giris sayfasi

## API Endpoint'leri

### Yetkilendirme
- `POST /login` - giris
- `GET /logout` - cikis
- `GET /api/whoami` - mevcut kullanici

### Hastalar
- `POST /api/patients` - yeni hasta (doktor + admin)
- `GET /api/patients` - liste (sadece admin)
- `GET /api/patients/<id>` - detay (sahip doktor + admin)
- `PUT /api/patients/<id>` - guncelle (sahip doktor + admin)
- `DELETE /api/patients/<id>` - sil (sadece admin)
- `GET /api/patients/stats` - istatistik (sadece admin)
- `GET /api/patients/export-csv` - CSV export (sadece admin)

### Preop (AO siniflama)
- `POST /api/preop/<patient_id>/analyze` - grafi yukle
- `PUT /api/preop/<patient_id>/correct` - manuel duzeltme
- `DELETE /api/preop/<patient_id>`

### Postop (PFN keypoint)
- `POST /api/postop/<patient_id>/analyze` - grafi yukle (view_type: AP/LAT)
- `POST /api/postop/<analysis_id>/recalculate` - yeniden hesapla
- `DELETE /api/postop/<analysis_id>`
- `GET /api/postop/<patient_id>/combined` - toplam TAD

## Database Semasi (Sade)

- `patients`: id, age, sex, side, nail_brand, outcome, created_by
- `preop_analyses`: ai_class, confidence, bbox, manual_class
- `postop_analyses`: keypoints, TAD, NSA, Cleveland, Parker, risk_score

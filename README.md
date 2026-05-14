# PFN Klinik Arastirma Platformu v2

Pertrochanteric femur fracture (PFN) sonrasi mekanik failure riskini AI ile degerlendiren klinik arastirma platformu.

## Ozellikler

- **Preop AO Siniflama AI**: Kirik grafilerinde 31-A1/A2/A3/B/normal siniflamasi
- **Postop PFN Keypoint AI**: 9 anatomik landmark tespit (AP + LAT)
- **TAD-AP**: Baumgaertner formulu (anatomic_neck_axis apex)
- **TAD Toplam**: AP + LAT toplami (orijinal Baumgaertner)
- **NSA, Cleveland Zon, Parker AP**: Otomatik hesaplama
- **Risk Skoru**: Multi-faktor degerlendirme (0-100)
- **Hasta Kaydi**: Demografik + klinik + cerrahi bilgiler
- **Takip Modulu**: Cut-out, mortality, Harris Hip Score
- **Manuel Duzeltme**: Tum AI ciktiları cerrah tarafindan duzeltilebilir
- **DICOM Destegi**: PixelSpacing otomatik kullanim

## Teknoloji

- **Backend**: Flask 3.0, SQLAlchemy, Flask-Migrate, PostgreSQL
- **AI**: YOLOv8 (Ultralytics) - 2 model
- **Frontend**: Vanilla JS, HTML5 Canvas
- **Deploy**: Railway + GitHub

---

## RAILWAY DEPLOY ADIM ADIM

### 1. GitHub'a Yukleme

```bash
# 1. GitHub'da yeni repo olusturun (orn: pfn-clinical-platform)
# 2. Bu klasoru git'e ekleyin:

cd /yol/pfn_system_v2
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/KULLANICI/pfn-clinical-platform.git
git push -u origin main
```

⚠️ **Onemli**: `models_files/*.pt` dosyalari `.gitignore` ile engellenir - GitHub'a YUKLENMEZ. Modelleri Railway'e ayri yukleyecegiz (asagidaki Adim 5).

### 2. Railway'de Proje Olusturma

1. https://railway.app adresine giris yapin
2. **New Project** -> **Deploy from GitHub repo**
3. `pfn-clinical-platform` repo'sunu secin
4. Railway otomatik olarak:
   - Python projesi oldugunu algilar
   - `requirements.txt`'i okur, paketleri kurar
   - `Procfile`'i okur, gunicorn ile baslar

### 3. PostgreSQL Eklemek

1. Projede **+ New** -> **Database** -> **Add PostgreSQL**
2. Railway otomatik olarak `DATABASE_URL` environment variable'ini olusturur
3. Bu degisken uygulamaya otomatik enjekte edilir

### 4. Environment Variables

Railway proje sayfasinda **Variables** sekmesinde:

| Variable | Deger |
|----------|-------|
| `SECRET_KEY` | Uzun rastgele string (orn: `openssl rand -hex 32` ciktisi) |
| `DATABASE_URL` | (PostgreSQL eklendiyse otomatik gelir) |

`SECRET_KEY` ornegi: `7f8a9b3c2d1e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9`

### 5. Model Dosyalarini Yukleme

⚠️ **EN ONEMLI ADIM**: `best.pt` ve `femur_model.pt` dosyalari Railway'e ayri yuklenmeli.

#### Yontem A: Railway CLI ile (ONERILEN)

```bash
# Railway CLI kurulumu (bir kez)
npm install -g @railway/cli

# Login
railway login

# Projeyi link et
cd /yol/pfn_system_v2
railway link

# Modelleri ortam degiskenleri ile kopyala (servis icinde calistir)
railway run bash
# Servis terminalinde:
mkdir -p models_files
# Yerel dosyalari upload edemiyoruz CLI ile; alternatif yontem asagida
```

#### Yontem B: Volume Mount (ONERILEN ALTERNATIF)

1. Railway'de servisin **Settings** -> **Volumes** kismina gidin
2. **+ Add Volume** -> Mount Path: `/app/models_files`
3. Volume olustuktan sonra **Mount and Edit** ile dosyalari yukleyebilirsiniz
4. `best.pt` ve `femur_model.pt`'yi bu volume'a yukleyin

#### Yontem C: Geçici - GitHub LFS

GitHub LFS ile model dosyalarini repo'ya da koyabilirsiniz (her dosya <100 MB ise):

```bash
git lfs install
git lfs track "*.pt"
git add .gitattributes
# .gitignore'dan models_files/*.pt satirini cikarin
git add models_files/best.pt models_files/femur_model.pt
git commit -m "Add AI models via LFS"
git push
```

### 6. Database Migration

Railway'de **release komutu** otomatik calisir (`Procfile`'da tanimli):
```
release: flask db upgrade || flask init-db
```

Bu komut ilk deploy'da tablolari olusturur.

Eger calismazsa manuel:
```bash
railway run flask init-db
```

### 7. Domain Olusturma

1. Railway'de servisin **Settings** -> **Networking**
2. **Generate Domain** -> Otomatik bir URL alirsiniz (orn: `pfn-clinical-platform.up.railway.app`)
3. Veya kendi domain'inizi baglayin

### 8. Test

Tarayicidan domain'i acin:

- `/` - Hasta listesi
- `/new-patient` - Yeni hasta formu
- `/dashboard` - Istatistikler
- `/health` - Saglik kontrolu (database baglantisini test eder)

---

## API Endpoint'leri

### Hastalar
- `POST   /api/patients` - Yeni hasta
- `GET    /api/patients` - Liste (sayfalandirma + filtre)
- `GET    /api/patients/<id>` - Detay (analiz + takip dahil)
- `PUT    /api/patients/<id>` - Guncelle
- `DELETE /api/patients/<id>` - Sil
- `POST   /api/patients/<id>/surgery` - Cerrahi bilgi
- `GET    /api/patients/stats` - Istatistik

### Preop (AO Siniflama)
- `POST   /api/preop/<patient_id>/analyze` - Grafi yukle ve AI ile siniflama
- `PUT    /api/preop/<patient_id>/correct` - Manuel duzeltme
- `GET    /api/preop/<patient_id>` - Preop analizi getir
- `DELETE /api/preop/<patient_id>` - Sil

### Postop (PFN Keypoint)
- `POST   /api/postop/<patient_id>/analyze` - Grafi yukle (view_type: AP/LAT)
- `POST   /api/postop/<analysis_id>/recalculate` - Manuel duzeltmelerle yeniden hesapla
- `GET    /api/postop/<analysis_id>` - Detay
- `DELETE /api/postop/<analysis_id>` - Sil
- `GET    /api/postop/<patient_id>/combined` - Toplam TAD (AP + LAT)

### Takip (Followup)
- `POST   /api/followup/<patient_id>` - Takip ekle
- `GET    /api/followup/<patient_id>` - Hastanin tum takipleri
- `PUT    /api/followup/<followup_id>/update` - Guncelle
- `DELETE /api/followup/<followup_id>` - Sil
- `GET    /api/followup/stats/outcomes` - Outcome istatistikleri

### Sistem
- `GET /health` - Saglik kontrolu

---

## Database Semasi

5 ana tablo:

| Tablo | Aciklama |
|-------|----------|
| `patients` | Hasta demografik + klinik bilgiler |
| `surgeries` | Cerrahi detaylar (civi markasi, lag screw vb.) |
| `preop_analyses` | AO siniflama AI sonuclari |
| `postop_analyses` | PFN keypoint AI sonuclari (AP/LAT) |
| `followups` | Takip kayitlari |

İliski: 1 hasta -> 1 cerrahi, 1 preop, N postop, N takip

---

## Yerel Test (Opsiyonel)

Sisteme yerel olarak da deploy edilebilir:

```bash
# PostgreSQL gerekli (veya SQLite ile fallback)
pip install -r requirements.txt

# Modelleri models_files/ klasorune kopyalayin
# best.pt + femur_model.pt

# .env dosyasi olusturun (.env.example baz alarak)
export DATABASE_URL="sqlite:///pfn_local.db"  # veya PostgreSQL
export SECRET_KEY="dev-secret"

# Database
flask init-db

# Calistir
python app.py
```

Tarayici: http://localhost:5000

---

## Sorun Giderme

### "AI model bulunamadi" hatasi
- `models_files/best.pt` ve `models_files/femur_model.pt` Railway'e yuklenmis mi kontrol edin
- Railway'de `railway run ls models_files/` calistirip dosyalari gorun

### "DATABASE_URL not set" hatasi
- Railway PostgreSQL servisinin eklendiginden emin olun
- **Variables** sekmesinde `DATABASE_URL` gozukmeli

### Yavas yukleme (ilk istekte)
- AI modelleri **lazy load** edilir - ilk istekte 10-30 saniye surebilir
- Sonraki istekler hizli olur (~1-2 saniye)

### "Out of memory" hatasi
- YOLOv8 ~450 MB RAM kullanır
- Railway Free tier 512 MB sinirlidir - **Hobby plan ($5/ay, 8 GB RAM) onerilir**

---

## Lisans ve Kullanim

Bu sistem klinik arastirma amacli gelistirilmistir. **Klinik karar destek sistemi** olarak kullanim icin etik kurul onayi gereklidir.

---

## Iletisim

**Geliştirici**: Doc. Dr. Ozgur Karakoyun  
Ortopedi ve Travmatoloji, Tekirdag

---

## Sistem Mimarisi (Ozet)

```
Doktor -> Web UI
            |
            v
       Flask Backend (Railway)
       /        |         \
      v         v          v
  Patients   Preop AI    Postop AI
  Surgery    (AO Class)  (PFN Keypoint)
  Followups  femur_model best.pt
            \    |    /
             v   v   v
        PostgreSQL (Railway)
```

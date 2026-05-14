"""
Model indirici - Google Drive'dan modelleri otomatik indirir.
Railway'de uygulama baslarken calisir.
Modeller zaten varsa indirmez (idempotent).
"""
import os
from pathlib import Path
import urllib.request
import ssl
import re

MODELS_DIR = Path(__file__).parent.parent / 'models_files'
MODELS_DIR.mkdir(parents=True, exist_ok=True)


# Model konfigurasyonu - Google Drive file ID'leri environment variable'dan
# YEDEKLENMIS DEFAULT degerler (Hocam'in paylastigi linkler):
MODELS = {
    'best.pt': {
        'file_id': os.environ.get('MODEL_BEST_PT_ID', '1c_cnifMoBOoeXE_9z-16FW6f28r3-y9H'),
        'min_size_mb': 20,  # 24 MB beklenir
        'expected_size_mb': 24,
    },
    'femur_model.pt': {
        'file_id': os.environ.get('MODEL_FEMUR_PT_ID', '1im2ffLqePb9uyR07AeR7HREE8efEibzr'),
        'min_size_mb': 80,  # 87 MB beklenir
        'expected_size_mb': 88,
    },
}


def download_from_google_drive(file_id, dest_path):
    """
    Google Drive public file ID'sinden dosya indir.
    Buyuk dosyalar icin virus tarama bypass yapilir.
    """
    base_url = "https://drive.google.com/uc?export=download"
    
    # SSL context (Railway'de cert sorunu olursa)
    ctx = ssl.create_default_context()
    
    # Ilk istek - confirm token al
    url = f"{base_url}&id={file_id}"
    
    print(f"  Indiriliyor: {url}")
    
    # User agent ekle - Google bazen bot block ediyor
    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as response:
            # Buyuk dosya ise Google "are you sure?" sayfasi gosterir
            content_type = response.headers.get('Content-Type', '')
            
            if 'text/html' in content_type:
                # HTML - confirm token gerekli
                html = response.read().decode('utf-8', errors='ignore')
                
                # confirm token'i bul
                # Google'in yeni format: action="https://drive.usercontent.google.com/download" hidden inputs
                match = re.search(r'confirm=([0-9A-Za-z_-]+)', html)
                if not match:
                    # Alternatif: form action ile farkli URL
                    match = re.search(r'href="(/uc\?export=download[^"]+)"', html)
                    if match:
                        confirmed_url = "https://drive.google.com" + match.group(1).replace('&amp;', '&')
                    else:
                        # Son care - usercontent download URL'i
                        confirmed_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
                else:
                    confirm = match.group(1)
                    confirmed_url = f"{base_url}&confirm={confirm}&id={file_id}"
                
                print(f"  Buyuk dosya, confirm gerekli: {confirmed_url[:80]}...")
                
                req2 = urllib.request.Request(confirmed_url, headers=headers)
                with urllib.request.urlopen(req2, context=ctx, timeout=300) as response2:
                    _save_response_to_file(response2, dest_path)
            else:
                # Direkt binary (kucuk dosya)
                _save_response_to_file(response, dest_path)
        
        return True
    except Exception as e:
        print(f"  HATA: {e}")
        return False


def _save_response_to_file(response, dest_path):
    """Response'u dosyaya yaz, ilerleme goster"""
    total = response.headers.get('Content-Length')
    if total:
        total = int(total)
    
    downloaded = 0
    chunk_size = 1024 * 1024  # 1 MB
    
    with open(dest_path, 'wb') as f:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            
            # Ilerleme yazdir (her 10 MB'de)
            if downloaded % (10 * 1024 * 1024) < chunk_size:
                mb = downloaded / (1024 * 1024)
                if total:
                    total_mb = total / (1024 * 1024)
                    print(f"  ... {mb:.1f}/{total_mb:.1f} MB")
                else:
                    print(f"  ... {mb:.1f} MB")
    
    final_mb = downloaded / (1024 * 1024)
    print(f"  Indirme tamamlandi: {final_mb:.1f} MB")


def ensure_models():
    """
    Tum modellerin indirilmis oldugundan emin ol.
    Eksik veya kucuk olanlari indir.
    """
    print("=" * 60)
    print("[MODEL DOWNLOADER] Modeller kontrol ediliyor...")
    print("=" * 60)
    
    for filename, config in MODELS.items():
        dest = MODELS_DIR / filename
        
        # Dosya var mi ve dogru boyutta mi?
        if dest.exists():
            size_mb = dest.stat().st_size / (1024 * 1024)
            if size_mb >= config['min_size_mb']:
                print(f"[OK] {filename}: {size_mb:.1f} MB (zaten var)")
                continue
            else:
                print(f"[ESKI] {filename}: {size_mb:.1f} MB - cok kucuk, yeniden indiriliyor")
                dest.unlink()
        
        # Indir
        print(f"[INDIR] {filename} (~{config['expected_size_mb']} MB) - file_id: {config['file_id']}")
        
        success = download_from_google_drive(config['file_id'], dest)
        
        if success and dest.exists():
            size_mb = dest.stat().st_size / (1024 * 1024)
            if size_mb >= config['min_size_mb']:
                print(f"[OK] {filename}: {size_mb:.1f} MB indirildi")
            else:
                print(f"[HATA] {filename}: sadece {size_mb:.1f} MB indi (en az {config['min_size_mb']} MB beklenir)")
                # Eksik veya yanlis dosya - silmiyoruz, kullanici manuel mudahale edebilir
        else:
            print(f"[HATA] {filename} indirilemedi")
    
    print("=" * 60)


if __name__ == '__main__':
    # Test calistirma
    ensure_models()

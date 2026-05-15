"""
Model indirici - gdown kutuphanesi ile Google Drive'dan modelleri indirir.
gdown buyuk dosyalar icin confirmation handling icerir (test edilmis).
"""
import os
from pathlib import Path

MODELS_DIR = Path(__file__).parent / 'models_files'
MODELS_DIR.mkdir(parents=True, exist_ok=True)


MODELS = {
    'best.pt': {
        'file_id': os.environ.get('MODEL_BEST_PT_ID', '1c_cnifMoBOoeXE_9z-16FW6f28r3-y9H'),
        'min_size_mb': 20,
        'expected_size_mb': 24,
    },
    'femur_model.pt': {
        'file_id': os.environ.get('MODEL_FEMUR_PT_ID', '1im2ffLqePb9uyR07AeR7HREE8efEibzr'),
        'min_size_mb': 80,
        'expected_size_mb': 88,
    },
}


def is_valid_pytorch_file(path):
    """Bir .pt dosyasinin gercek PyTorch dosyasi mi yoksa HTML mi oldugunu kontrol"""
    if not path.exists():
        return False
    
    try:
        with open(path, 'rb') as f:
            header = f.read(16)
    except:
        return False
    
    # PyTorch ZIP format
    if header.startswith(b'PK'):
        return True
    
    # HTML degil mi?
    if header.startswith(b'<!DOCTYPE') or header.startswith(b'<html') or header.startswith(b'<HTML'):
        return False
    
    # Eski PyTorch pickle format
    if header.startswith(b'\x80\x02') or header.startswith(b'\x80\x03') or header.startswith(b'\x80\x04'):
        return True
    
    # Tanidik degil ama HTML de degil - hicbir suretle silmedik, kabul edelim
    return True


def download_with_gdown(file_id, dest_path):
    """gdown kutuphanesi ile indir - Google Drive icin en saglam yontem"""
    try:
        import gdown
    except ImportError:
        print(f"  [HATA] gdown yuklu degil - requirements.txt'e ekleyin: gdown==5.2.0")
        return False
    
    url = f"https://drive.google.com/uc?id={file_id}"
    print(f"  gdown ile indiriliyor: {url}")
    
    try:
        result = gdown.download(url, str(dest_path), quiet=False, fuzzy=True)
        if result:
            return True
        else:
            print(f"  gdown.download None dondu")
            return False
    except Exception as e:
        print(f"  HATA: {e}")
        import traceback
        traceback.print_exc()
        return False


def ensure_models():
    """Tum modellerin indirildiginden ve gecerli oldugundan emin ol"""
    print("=" * 60)
    print("[MODEL DOWNLOADER] Modeller kontrol ediliyor...")
    print("=" * 60)
    
    success_count = 0
    
    for filename, config in MODELS.items():
        dest = MODELS_DIR / filename
        
        # Dosya var ve gecerli mi?
        if dest.exists():
            size_mb = dest.stat().st_size / (1024 * 1024)
            valid = is_valid_pytorch_file(dest)
            
            if size_mb >= config['min_size_mb'] and valid:
                print(f"[OK] {filename}: {size_mb:.1f} MB (zaten var)")
                success_count += 1
                continue
            else:
                reason = "boyut kucuk" if size_mb < config['min_size_mb'] else "gecersiz format"
                print(f"[ESKI/BOZUK] {filename}: {size_mb:.1f} MB ({reason}) - yeniden indiriliyor")
                dest.unlink()
        
        # Indir
        print(f"[INDIR] {filename} (~{config['expected_size_mb']} MB) - file_id: {config['file_id']}")
        
        success = download_with_gdown(config['file_id'], dest)
        
        if success and dest.exists():
            size_mb = dest.stat().st_size / (1024 * 1024)
            valid = is_valid_pytorch_file(dest)
            
            if size_mb >= config['min_size_mb'] and valid:
                print(f"[OK] {filename}: {size_mb:.1f} MB indirildi")
                success_count += 1
            elif not valid:
                print(f"[HATA] {filename}: gecersiz PyTorch dosyasi! Drive linki public olmali.")
                dest.unlink()
            else:
                print(f"[HATA] {filename}: sadece {size_mb:.1f} MB (en az {config['min_size_mb']} MB)")
                dest.unlink()
        else:
            print(f"[HATA] {filename} indirilemedi")
    
    print("=" * 60)
    print(f"[SONUC] {success_count}/{len(MODELS)} model hazir")
    print("=" * 60)


if __name__ == '__main__':
    ensure_models()

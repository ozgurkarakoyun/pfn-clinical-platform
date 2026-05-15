"""
Storage helper - Cloudinary VARSA oraya yukle (kalici), yoksa lokal static/uploads (ephemeral).
Bu sayede Railway redeploy'lari grafileri silmez.

Setup:
  Railway Environment Variables:
    CLOUDINARY_CLOUD_NAME=...
    CLOUDINARY_API_KEY=...
    CLOUDINARY_API_SECRET=...
  
  Bu degiskenler yoksa otomatik olarak lokal storage kullanir.
"""
import os
from pathlib import Path
from datetime import datetime
import uuid

# Lokal upload path
UPLOAD_DIR = Path(__file__).parent / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Cloudinary konfigurasyon
_cloudinary_enabled = False
_cloudinary_client = None


def _init_cloudinary():
    """Cloudinary'i baslat - environment variables varsa"""
    global _cloudinary_enabled, _cloudinary_client
    
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    api_key = os.environ.get('CLOUDINARY_API_KEY')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    
    if not (cloud_name and api_key and api_secret):
        print("[STORAGE] Cloudinary yapilandirilmamis - lokal storage kullanilacak")
        print("[STORAGE] UYARI: Lokal storage Railway redeploy'larinda KAYBOLUR")
        return False
    
    try:
        import cloudinary
        import cloudinary.uploader
        
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True
        )
        _cloudinary_enabled = True
        _cloudinary_client = cloudinary
        print(f"[STORAGE] Cloudinary aktif: {cloud_name}")
        return True
    except Exception as e:
        print(f"[STORAGE] Cloudinary baslatma hatasi: {e}")
        return False


# Modul yuklenirken bir kez calistir
_init_cloudinary()


def save_image_jpg(pil_image, prefix='img', patient_id=None, quality=85):
    """
    PIL Image'i optimize JPG olarak kaydet.
    
    Cloudinary varsa: oraya yukler, secure URL doner
    Yoksa: static/uploads/ icine kaydeder, /static/uploads/X.jpg URL'i doner
    
    Returns: dict with 'url' (frontend icin), 'storage_id' (silme icin), 'storage_type'
    """
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    pid_part = f"_{patient_id}" if patient_id else ""
    filename = f"{prefix}{pid_part}_{timestamp}_{unique_id}.jpg"
    
    if _cloudinary_enabled and _cloudinary_client:
        return _save_to_cloudinary(pil_image, filename, quality)
    else:
        return _save_to_local(pil_image, filename, quality)


def _save_to_local(pil_image, filename, quality):
    """Lokal static/uploads/'a kaydet"""
    save_path = UPLOAD_DIR / filename
    
    # JPG optimize ile kaydet (hafiza tasarrufu)
    pil_image.save(save_path, 'JPEG', quality=quality, optimize=True, progressive=True)
    
    size_kb = save_path.stat().st_size / 1024
    print(f"[STORAGE LOCAL] {filename}: {size_kb:.1f} KB (quality={quality})")
    
    return {
        'url': f'/static/uploads/{filename}',
        'storage_id': filename,
        'storage_type': 'local',
        'size_bytes': save_path.stat().st_size,
    }


def _save_to_cloudinary(pil_image, filename, quality):
    """Cloudinary'e yukle"""
    from io import BytesIO
    
    # PIL Image -> BytesIO
    buffer = BytesIO()
    pil_image.save(buffer, 'JPEG', quality=quality, optimize=True, progressive=True)
    buffer.seek(0)
    
    # Cloudinary'e yukle
    # public_id = filename'in uzantisiz hali
    public_id = filename.replace('.jpg', '')
    folder = 'pfn-platform'  # Tum upload'lar tek klasor altinda
    
    try:
        result = _cloudinary_client.uploader.upload(
            buffer,
            public_id=public_id,
            folder=folder,
            resource_type='image',
            format='jpg',
            quality='auto:good',  # Cloudinary akilli kalite
            fetch_format='auto',  # WebP/AVIF otomatik (modern tarayicilarda)
        )
        
        secure_url = result.get('secure_url')
        size_kb = result.get('bytes', 0) / 1024
        full_public_id = result.get('public_id')
        
        print(f"[STORAGE CLOUDINARY] {filename}: {size_kb:.1f} KB - {secure_url}")
        
        return {
            'url': secure_url,
            'storage_id': full_public_id,  # Silme icin tam id (folder/filename)
            'storage_type': 'cloudinary',
            'size_bytes': result.get('bytes', 0),
        }
    except Exception as e:
        print(f"[STORAGE CLOUDINARY HATA] {e} - lokal'e fallback")
        # Cloudinary hata verdi, lokal'e fallback
        pil_image.seek(0) if hasattr(pil_image, 'seek') else None
        return _save_to_local(pil_image, filename, quality)


def delete_image(storage_id, storage_type='local'):
    """Bir grafi sil"""
    if storage_type == 'cloudinary' and _cloudinary_enabled:
        try:
            _cloudinary_client.uploader.destroy(storage_id, resource_type='image')
            print(f"[STORAGE CLOUDINARY] silindi: {storage_id}")
            return True
        except Exception as e:
            print(f"[STORAGE CLOUDINARY DELETE HATA] {e}")
            return False
    else:
        # Local
        path = UPLOAD_DIR / storage_id
        if path.exists():
            path.unlink()
            print(f"[STORAGE LOCAL] silindi: {storage_id}")
            return True
        return False


def get_storage_info():
    """Durum bilgisi (debug icin)"""
    return {
        'cloudinary_enabled': _cloudinary_enabled,
        'cloud_name': os.environ.get('CLOUDINARY_CLOUD_NAME', '-'),
        'local_dir': str(UPLOAD_DIR),
        'local_file_count': len(list(UPLOAD_DIR.glob('*.jpg'))) if UPLOAD_DIR.exists() else 0,
    }

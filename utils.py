import os
import re
import uuid
import logging
from urllib.parse import urlparse

from config import TEMP_DOWNLOAD_DIR

logger = logging.getLogger(__name__)

def extract_url(text):
    """استخراج URL از متن ارسال شده"""
    # الگوی URL استاندارد
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
    
    # یافتن URL ها در متن
    urls = re.findall(url_pattern, text)
    
    if not urls:
        # اگر URL پیدا نشد، ممکن است کاربر لینک را بدون پروتکل ارسال کرده باشد
        # سعی می‌کنیم الگوهای رایج را بررسی کنیم
        common_domains = [
            r'(?:www\.)?instagram\.com/[\w.-]+/(?:p|reel)/[\w-]+',     # Instagram posts and reels
            r'(?:www\.)?instagram\.com/stories/[\w.-]+/\d+',           # Instagram stories
            r'(?:www\.)?youtube\.com/watch\?v=[\w-]+',                 # YouTube videos
            r'youtu\.be/[\w-]+',                                       # YouTube shortened URLs
            r'(?:www\.)?youtube\.com/shorts/[\w-]+'                    # YouTube shorts
        ]
        
        for pattern in common_domains:
            potential_url = re.search(pattern, text)
            if potential_url:
                return 'https://' + potential_url.group(0)
    
    # اگر URL استاندارد پیدا شد
    if urls:
        # بررسی کنیم که URL یوتیوب کامل است یا فقط دامنه اصلی
        for url in urls:
            # برای شناسایی یک URL کامل یوتیوب
            if '/shorts/' in url:
                # اطمینان از اینکه بعد از /shorts/ یک شناسه وجود دارد
                match = re.search(r'youtube\.com/shorts/([\w-]+)', url)
                if match and match.group(1):
                    logger.info(f"URL شورتز یوتیوب پیدا شد: {url}")
                    return url
            
            # برای ویدیوهای عادی یوتیوب
            if '/watch?v=' in url:
                match = re.search(r'[?&]v=([\w-]+)', url)
                if match and match.group(1):
                    logger.info(f"URL ویدیوی یوتیوب پیدا شد: {url}")
                    return url
            
            # برای لینک‌های کوتاه یوتیوب
            if 'youtu.be/' in url:
                match = re.search(r'youtu\.be/([\w-]+)', url)
                if match and match.group(1):
                    logger.info(f"URL کوتاه یوتیوب پیدا شد: {url}")
                    return url
            
            # برای لینک‌های اینستاگرام
            if 'instagram.com/' in url:
                logger.info(f"URL اینستاگرام پیدا شد: {url}")
                return url
        
        # اگر هیچ یک از شرایط بالا صادق نبود، اولین URL را برمی‌گردانیم
        logger.info(f"URL پیدا شد: {urls[0]}")
        return urls[0]
    
    logger.warning(f"هیچ URL در متن پیدا نشد: {text}")
    return None

def is_instagram_url(url):
    """بررسی می‌کند که آیا URL مربوط به اینستاگرام است یا خیر"""
    parsed_url = urlparse(url)
    return any(domain in parsed_url.netloc for domain in ['instagram.com', 'www.instagram.com', 'instagr.am'])

def is_youtube_url(url):
    """بررسی می‌کند که آیا URL مربوط به یوتیوب است یا خیر"""
    parsed_url = urlparse(url)
    return any(domain in parsed_url.netloc for domain in ['youtube.com', 'www.youtube.com', 'youtu.be'])

def is_youtube_shorts(url):
    """بررسی می‌کند که آیا URL مربوط به شورتز یوتیوب است یا خیر"""
    # تشخیص دقیق‌تر شورتز یوتیوب با استفاده از regex
    if not url:
        return False
        
    # بررسی الگوی /shorts/ در URL
    shorts_pattern = r'youtube\.com/shorts/[\w-]+'
    is_shorts = bool(re.search(shorts_pattern, url))
    
    if is_shorts:
        logger.info(f"لینک شورتز یوتیوب شناسایی شد: {url}")
    
    return is_shorts

def generate_temp_filename(extension='.mp4'):
    """ایجاد یک نام فایل موقت با پسوند مشخص"""
    random_name = str(uuid.uuid4())
    return os.path.join(TEMP_DOWNLOAD_DIR, f"{random_name}{extension}")

def clean_temp_file(file_path):
    """پاک کردن فایل موقت بعد از استفاده"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"فایل موقت حذف شد: {file_path}")
    except Exception as e:
        logger.error(f"خطا در حذف فایل موقت {file_path}: {e}")

def get_file_size(file_path):
    """دریافت سایز فایل به بایت"""
    return os.path.getsize(file_path) if os.path.exists(file_path) else 0

def format_size(size_bytes):
    """تبدیل سایز از بایت به واحد خوانا"""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024
        i += 1
    return f"{size_bytes:.2f} {size_name[i]}"
    
def convert_video_to_audio(video_path, output_extension='.mp3'):
    """تبدیل ویدیو به فایل صوتی"""
    import subprocess
    
    # تولید نام فایل صوتی خروجی
    audio_path = generate_temp_filename(output_extension)
    
    try:
        # استفاده از ffmpeg برای استخراج صدا با کیفیت بالا
        cmd = [
            'ffmpeg', '-i', video_path, 
            '-q:a', '0', '-map', 'a',
            audio_path, '-y'
        ]
        
        # اجرای دستور ffmpeg
        subprocess.run(cmd, check=True, capture_output=True)
        
        # بررسی وجود فایل خروجی
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"فایل صوتی با موفقیت ایجاد شد: {audio_path}")
            return audio_path
        else:
            logger.error("خطا در تبدیل ویدیو به صدا: فایل خروجی ایجاد نشد یا خالی است")
            return None
            
    except Exception as e:
        logger.error(f"خطا در تبدیل ویدیو به صدا: {e}")
        logger.exception("جزئیات خطا:")
        return None

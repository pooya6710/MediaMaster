import os
import re
import uuid
import logging
from urllib.parse import urlparse

from config import TEMP_DOWNLOAD_DIR

logger = logging.getLogger(__name__)

def extract_url(text):
    """استخراج URL از متن ارسال شده"""
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
    urls = re.findall(url_pattern, text)
    return urls[0] if urls else None

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
    return 'shorts' in url

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

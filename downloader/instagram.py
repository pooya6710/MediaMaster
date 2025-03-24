import os
import re
import time
import logging
import requests
import tempfile
import instaloader
from typing import List, Tuple, Dict, Any, Optional
from instaloader.exceptions import ProfileNotExistsException, PrivateProfileNotFollowedException

from config import TEMP_DOWNLOAD_DIR
from utils import generate_temp_filename, clean_temp_file

logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        """راه‌اندازی کلاس دانلودر اینستاگرام"""
        self.loader = instaloader.Instaloader(
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            filename_pattern='{profile}_{shortcode}'
        )
        # ایجاد مسیر ذخیره موقت
        if not os.path.exists(TEMP_DOWNLOAD_DIR):
            os.makedirs(TEMP_DOWNLOAD_DIR)
    
    def _extract_shortcode_from_url(self, url: str) -> Optional[str]:
        """استخراج کد کوتاه از لینک پست اینستاگرام"""
        # الگوهای مختلف URL اینستاگرام
        patterns = [
            r'instagram.com/p/([^/?#&]+)',          # پست عادی
            r'instagram.com/reel/([^/?#&]+)',       # ریلز
            r'instagram.com/tv/([^/?#&]+)',         # IGTV
            r'instagram.com/stories/[^/]+/([^/?#&]+)'  # استوری
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def download_post(self, url: str) -> List[str]:
        """دانلود پست اینستاگرام (تصویر یا ویدیو)"""
        try:
            shortcode = self._extract_shortcode_from_url(url)
            if not shortcode:
                logger.error(f"کد کوتاه از URL استخراج نشد: {url}")
                return []
            
            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            
            # مسیر فایل‌های دانلود شده
            downloaded_files = []
            
            # ایجاد مسیر موقت برای دانلود
            with tempfile.TemporaryDirectory() as tmpdirname:
                self.loader.dirname_pattern = tmpdirname
                
                try:
                    self.loader.download_post(post, target=shortcode)
                    
                    # یافتن فایل‌های دانلود شده در مسیر موقت
                    for root, _, files in os.walk(os.path.join(tmpdirname, shortcode)):
                        for file in files:
                            # فقط فایل‌های عکس و ویدیو را انتخاب می‌کنیم
                            if file.endswith(('.jpg', '.mp4')):
                                source_path = os.path.join(root, file)
                                
                                # تعیین پسوند فایل
                                file_ext = os.path.splitext(file)[1]
                                target_path = generate_temp_filename(file_ext)
                                
                                # کپی فایل به مسیر هدف
                                with open(source_path, 'rb') as src_file:
                                    with open(target_path, 'wb') as dst_file:
                                        dst_file.write(src_file.read())
                                
                                downloaded_files.append(target_path)
                
                except PrivateProfileNotFollowedException:
                    logger.error(f"پروفایل خصوصی است: {url}")
                    raise PrivateProfileNotFollowedException("این پروفایل خصوصی است")
                
                except Exception as e:
                    logger.error(f"خطا در دانلود پست اینستاگرام {url}: {e}")
                    raise
            
            return downloaded_files
        
        except Exception as e:
            logger.error(f"خطا در دانلود از اینستاگرام: {e}")
            raise
    
    def download_reel(self, url: str) -> str:
        """دانلود ریلز اینستاگرام"""
        return self.download_post(url)[0] if self.download_post(url) else ""
    
    def clean_up(self, file_paths: List[str]) -> None:
        """پاک کردن فایل‌های موقت"""
        for file_path in file_paths:
            clean_temp_file(file_path)

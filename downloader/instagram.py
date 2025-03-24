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
            logger.info(f"شروع دانلود از اینستاگرام با URL: {url}")
            shortcode = self._extract_shortcode_from_url(url)
            if not shortcode:
                logger.error(f"کد کوتاه از URL استخراج نشد: {url}")
                return []
            
            logger.info(f"کد کوتاه استخراج شده: {shortcode}")
            
            try:
                logger.info("در حال دریافت اطلاعات پست...")
                post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
                logger.info(f"اطلاعات پست دریافت شد: {post.mediaid}")
            except Exception as post_error:
                logger.error(f"خطا در دریافت اطلاعات پست: {post_error}")
                return []
            
            # مسیر فایل‌های دانلود شده
            downloaded_files = []
            
            # ایجاد مسیر موقت برای دانلود
            with tempfile.TemporaryDirectory() as tmpdirname:
                logger.info(f"مسیر موقت ایجاد شد: {tmpdirname}")
                self.loader.dirname_pattern = tmpdirname
                
                try:
                    logger.info("در حال دانلود پست...")
                    self.loader.download_post(post, target=shortcode)
                    logger.info("پست با موفقیت دانلود شد")
                    
                    # یافتن فایل‌های دانلود شده در مسیر موقت
                    target_dir = os.path.join(tmpdirname, shortcode)
                    logger.info(f"بررسی فایل‌های دانلود شده در: {target_dir}")
                    
                    if not os.path.exists(target_dir):
                        logger.warning(f"مسیر هدف وجود ندارد: {target_dir}")
                        # سعی می‌کنیم همه فایل‌ها در مسیر اصلی را بررسی کنیم
                        target_dir = tmpdirname
                    
                    for root, _, files in os.walk(target_dir):
                        logger.info(f"فایل‌های یافت شده: {files}")
                        for file in files:
                            # فقط فایل‌های عکس و ویدیو را انتخاب می‌کنیم
                            if file.endswith(('.jpg', '.mp4')):
                                source_path = os.path.join(root, file)
                                logger.info(f"فایل یافت شد: {source_path}")
                                
                                # تعیین پسوند فایل
                                file_ext = os.path.splitext(file)[1]
                                target_path = generate_temp_filename(file_ext)
                                
                                # کپی فایل به مسیر هدف
                                with open(source_path, 'rb') as src_file:
                                    with open(target_path, 'wb') as dst_file:
                                        dst_file.write(src_file.read())
                                
                                logger.info(f"فایل کپی شد به: {target_path}")
                                downloaded_files.append(target_path)
                    
                    if not downloaded_files:
                        logger.warning("هیچ فایلی دانلود نشد!")
                
                except PrivateProfileNotFollowedException as private_error:
                    logger.error(f"پروفایل خصوصی است: {url}")
                    raise PrivateProfileNotFollowedException("این پروفایل خصوصی است") from private_error
                
                except Exception as download_error:
                    logger.error(f"خطا در دانلود پست اینستاگرام {url}: {download_error}")
                    raise download_error
            
            logger.info(f"تعداد فایل‌های دانلود شده: {len(downloaded_files)}")
            return downloaded_files
        
        except Exception as outer_error:
            logger.error(f"خطا در دانلود از اینستاگرام: {outer_error}")
            logger.exception("جزئیات خطا:")
            return []
    
    def download_reel(self, url: str) -> str:
        """دانلود ریلز اینستاگرام"""
        return self.download_post(url)[0] if self.download_post(url) else ""
    
    def clean_up(self, file_paths: List[str]) -> None:
        """پاک کردن فایل‌های موقت"""
        for file_path in file_paths:
            clean_temp_file(file_path)

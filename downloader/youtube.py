import os
import logging
import tempfile
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from pytube import YouTube
from pytube.exceptions import RegexMatchError, VideoUnavailable

from config import MAX_TELEGRAM_FILE_SIZE
from utils import generate_temp_filename, clean_temp_file, format_size

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    def __init__(self):
        """راه‌اندازی کلاس دانلودر یوتیوب"""
        pass
    
    def _get_video_id(self, url: str) -> Optional[str]:
        """استخراج شناسه ویدیو از URL یوتیوب"""
        try:
            parsed_url = urlparse(url)
            if parsed_url.netloc == 'youtu.be':
                return parsed_url.path[1:]
            elif parsed_url.netloc in ('youtube.com', 'www.youtube.com'):
                if '/watch' in parsed_url.path:
                    return parse_qs(parsed_url.query)['v'][0]
                elif '/shorts/' in parsed_url.path:
                    # استخراج شناسه ویدیو از شورتز
                    return parsed_url.path.split('/shorts/')[1]
                elif '/embed/' in parsed_url.path:
                    return parsed_url.path.split('/embed/')[1]
                elif '/v/' in parsed_url.path:
                    return parsed_url.path.split('/v/')[1]
            return None
        except Exception as e:
            logger.error(f"خطا در استخراج شناسه ویدیو: {e}")
            return None
    
    def get_available_streams(self, url: str) -> Dict[str, Tuple[str, int]]:
        """دریافت لیست استریم‌های موجود برای دانلود به همراه سایز آنها"""
        try:
            video_id = self._get_video_id(url)
            if not video_id:
                logger.error(f"شناسه ویدیو از URL استخراج نشد: {url}")
                return {}
            
            yt = YouTube(url)
            streams = {}
            
            # استخراج استریم‌های ویدیویی (با صدا و بدون صدا)
            video_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
            
            for stream in video_streams:
                # استخراج اطلاعات هر استریم
                resolution = stream.resolution
                if resolution not in streams:
                    filesize = stream.filesize
                    key = f"{resolution} ({format_size(filesize)})"
                    streams[key] = (stream.itag, filesize)
            
            return streams
        
        except VideoUnavailable:
            logger.error(f"ویدیو موجود نیست: {url}")
            return {}
        except RegexMatchError:
            logger.error(f"لینک یوتیوب نامعتبر است: {url}")
            return {}
        except Exception as e:
            logger.error(f"خطا در دریافت استریم‌های ویدیو: {e}")
            return {}
    
    def download_video(self, url: str, itag: int) -> str:
        """دانلود ویدیو با استفاده از شناسه استریم"""
        try:
            yt = YouTube(url)
            stream = yt.streams.get_by_itag(itag)
            
            if not stream:
                logger.error(f"استریم با شناسه {itag} یافت نشد برای {url}")
                return ""
            
            # بررسی سایز فایل
            if stream.filesize > MAX_TELEGRAM_FILE_SIZE:
                logger.warning(f"سایز فایل ({stream.filesize}) بیشتر از حد مجاز تلگرام است")
                return ""
            
            # تعیین نام فایل خروجی
            output_file = generate_temp_filename('.mp4')
            
            # دانلود و ذخیره ویدیو
            stream.download(filename=output_file)
            
            return output_file
        
        except Exception as e:
            logger.error(f"خطا در دانلود ویدیو: {e}")
            return ""
    
    def download_shorts(self, url: str) -> str:
        """دانلود شورتز یوتیوب"""
        try:
            yt = YouTube(url)
            
            # انتخاب بهترین کیفیت موجود برای دانلود
            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').first()
            
            if not stream:
                logger.error(f"استریمی برای دانلود شورتز یافت نشد: {url}")
                return ""
            
            # بررسی سایز فایل
            if stream.filesize > MAX_TELEGRAM_FILE_SIZE:
                logger.warning(f"سایز فایل شورتز ({stream.filesize}) بیشتر از حد مجاز تلگرام است")
                return ""
            
            # تعیین نام فایل خروجی
            output_file = generate_temp_filename('.mp4')
            
            # دانلود و ذخیره ویدیو
            stream.download(filename=output_file)
            
            return output_file
        
        except Exception as e:
            logger.error(f"خطا در دانلود شورتز: {e}")
            return ""
    
    def clean_up(self, file_path: str) -> None:
        """پاک کردن فایل موقت"""
        clean_temp_file(file_path)

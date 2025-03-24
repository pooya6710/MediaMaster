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
            # بررسی اینکه آیا لینک اصلی یوتیوب بدون هیچ ویدیویی خاص است
            if url.strip('/') in ['https://youtube.com', 'http://youtube.com', 
                              'https://www.youtube.com', 'http://www.youtube.com']:
                logger.warning(f"لینک ارسال شده فقط صفحه اصلی یوتیوب است: {url}")
                return None
            
            parsed_url = urlparse(url)
            
            # بررسی فرمت کوتاه youtu.be
            if parsed_url.netloc == 'youtu.be':
                video_id = parsed_url.path[1:]
                logger.info(f"شناسه ویدیو از لینک کوتاه: {video_id}")
                return video_id
                
            # بررسی انواع مختلف لینک‌های یوتیوب 
            elif parsed_url.netloc in ('youtube.com', 'www.youtube.com'):
                # ویدیوی عادی
                if '/watch' in parsed_url.path:
                    if 'v' in parse_qs(parsed_url.query):
                        video_id = parse_qs(parsed_url.query)['v'][0]
                        logger.info(f"شناسه ویدیو از لینک watch: {video_id}")
                        return video_id
                    
                # لینک شورتز
                elif '/shorts/' in parsed_url.path:
                    parts = parsed_url.path.split('/shorts/')
                    if len(parts) > 1 and parts[1]:
                        # حذف هرگونه پارامتر اضافی که ممکن است بعد از شناسه باشد
                        video_id = parts[1].split('/')[0]
                        logger.info(f"شناسه ویدیو از لینک شورتز: {video_id}")
                        return video_id
                    
                # لینک embeded
                elif '/embed/' in parsed_url.path:
                    parts = parsed_url.path.split('/embed/')
                    if len(parts) > 1 and parts[1]:
                        video_id = parts[1].split('/')[0]
                        logger.info(f"شناسه ویدیو از لینک embed: {video_id}")
                        return video_id
                        
                # فرمت v
                elif '/v/' in parsed_url.path:
                    parts = parsed_url.path.split('/v/')
                    if len(parts) > 1 and parts[1]:
                        video_id = parts[1].split('/')[0]
                        logger.info(f"شناسه ویدیو از لینک /v/: {video_id}")
                        return video_id
            
            logger.warning(f"هیچ شناسه ویدیویی در URL پیدا نشد: {url}")
            return None
            
        except Exception as e:
            logger.error(f"خطا در استخراج شناسه ویدیو: {e}")
            logger.exception("جزئیات خطا:")
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
            logger.info(f"شروع دانلود ویدیوی یوتیوب با URL: {url} و itag: {itag}")
            
            try:
                yt = YouTube(url)
                logger.info(f"اطلاعات ویدیو دریافت شد: {yt.title}")
            except Exception as yt_error:
                logger.error(f"خطا در دریافت اطلاعات ویدیو: {yt_error}")
                return ""
            
            try:
                stream = yt.streams.get_by_itag(itag)
                if not stream:
                    logger.error(f"استریم با شناسه {itag} یافت نشد برای {url}")
                    return ""
                logger.info(f"استریم با کیفیت {stream.resolution} و فرمت {stream.mime_type} یافت شد")
            except Exception as stream_error:
                logger.error(f"خطا در دریافت استریم: {stream_error}")
                return ""
            
            # بررسی سایز فایل
            try:
                filesize = stream.filesize
                logger.info(f"سایز فایل: {filesize} بایت ({format_size(filesize)})")
                if filesize > MAX_TELEGRAM_FILE_SIZE:
                    logger.warning(f"سایز فایل ({format_size(filesize)}) بیشتر از حد مجاز تلگرام است")
                    return ""
            except Exception as size_error:
                logger.error(f"خطا در دریافت سایز فایل: {size_error}")
                # ادامه می‌دهیم حتی اگر سایز را نتوانستیم بررسی کنیم
            
            # تعیین نام فایل خروجی
            output_file = generate_temp_filename('.mp4')
            logger.info(f"نام فایل خروجی: {output_file}")
            
            # دانلود و ذخیره ویدیو
            try:
                logger.info("در حال دانلود ویدیو...")
                stream.download(filename=output_file)
                
                # بررسی وجود فایل
                if not os.path.exists(output_file):
                    logger.error(f"فایل خروجی ایجاد نشد: {output_file}")
                    return ""
                
                file_size = os.path.getsize(output_file)
                logger.info(f"ویدیو با موفقیت دانلود شد. سایز فایل: {format_size(file_size)}")
                
                return output_file
            except Exception as download_error:
                logger.error(f"خطا در دانلود و ذخیره ویدیو: {download_error}")
                return ""
        
        except Exception as outer_error:
            logger.error(f"خطای کلی در دانلود ویدیو: {outer_error}")
            logger.exception("جزئیات خطا:")
            return ""
    
    def download_shorts(self, url: str) -> str:
        """دانلود شورتز یوتیوب"""
        try:
            logger.info(f"شروع دانلود شورتز یوتیوب با URL: {url}")
            
            try:
                yt = YouTube(url)
                logger.info(f"اطلاعات شورتز دریافت شد: {yt.title}")
            except Exception as yt_error:
                logger.error(f"خطا در دریافت اطلاعات شورتز: {yt_error}")
                return ""
            
            # انتخاب بهترین کیفیت موجود برای دانلود
            try:
                stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').first()
                if not stream:
                    logger.error(f"استریمی برای دانلود شورتز یافت نشد: {url}")
                    return ""
                logger.info(f"استریم با کیفیت {stream.resolution} و فرمت {stream.mime_type} یافت شد")
            except Exception as stream_error:
                logger.error(f"خطا در دریافت استریم شورتز: {stream_error}")
                return ""
            
            # بررسی سایز فایل
            try:
                filesize = stream.filesize
                logger.info(f"سایز فایل شورتز: {filesize} بایت ({format_size(filesize)})")
                if filesize > MAX_TELEGRAM_FILE_SIZE:
                    logger.warning(f"سایز فایل شورتز ({format_size(filesize)}) بیشتر از حد مجاز تلگرام است")
                    return ""
            except Exception as size_error:
                logger.error(f"خطا در دریافت سایز فایل شورتز: {size_error}")
                # ادامه می‌دهیم حتی اگر سایز را نتوانستیم بررسی کنیم
            
            # تعیین نام فایل خروجی
            output_file = generate_temp_filename('.mp4')
            logger.info(f"نام فایل خروجی شورتز: {output_file}")
            
            # دانلود و ذخیره ویدیو
            try:
                logger.info("در حال دانلود شورتز...")
                stream.download(filename=output_file)
                
                # بررسی وجود فایل
                if not os.path.exists(output_file):
                    logger.error(f"فایل خروجی شورتز ایجاد نشد: {output_file}")
                    return ""
                
                file_size = os.path.getsize(output_file)
                logger.info(f"شورتز با موفقیت دانلود شد. سایز فایل: {format_size(file_size)}")
                
                return output_file
            except Exception as download_error:
                logger.error(f"خطا در دانلود و ذخیره شورتز: {download_error}")
                return ""
        
        except Exception as e:
            logger.error(f"خطای کلی در دانلود شورتز: {e}")
            logger.exception("جزئیات خطا:")
            return ""
    
    def clean_up(self, file_path: str) -> None:
        """پاک کردن فایل موقت"""
        clean_temp_file(file_path)

import os
import re
import json
import logging
import tempfile
import requests
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
            yt.bypass_age_gate()  # تلاش برای بایپس محدودیت سنی
            streams = {}
            
            # استخراج استریم‌های ویدیویی (با صدا)
            video_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
            
            # استخراج استریم‌های ویدیویی با کیفیت بالا (بدون صدا)
            high_res_streams = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by('resolution').desc()
            
            # ابتدا استریم‌های با کیفیت معمولی (همراه با صدا) را اضافه می‌کنیم
            for stream in video_streams:
                resolution = stream.resolution
                if resolution not in streams:
                    try:
                        filesize = stream.filesize
                        key = f"{resolution} ({format_size(filesize)}) - با صدا"
                        streams[key] = (stream.itag, filesize)
                    except Exception as e:
                        logger.warning(f"خطا در دریافت اطلاعات استریم {stream.itag}: {e}")
                        continue
            
            # سپس استریم‌های با کیفیت بالا را اضافه می‌کنیم (حداکثر 3 مورد)
            count = 0
            for stream in high_res_streams:
                resolution = stream.resolution
                if resolution not in [s.split(" ")[0] for s in streams.keys()] and count < 3:
                    try:
                        filesize = stream.filesize
                        # برای کیفیت‌های بالا، تنها در صورتی که حجم آن کمتر از 50MB باشد اضافه می‌کنیم
                        if filesize < MAX_TELEGRAM_FILE_SIZE:
                            key = f"{resolution} ({format_size(filesize)}) - فقط تصویر"
                            streams[key] = (stream.itag, filesize)
                            count += 1
                    except Exception as e:
                        logger.warning(f"خطا در دریافت اطلاعات استریم {stream.itag}: {e}")
                        continue
            
            # اگر هیچ استریمی پیدا نشد، از yt-dlp استفاده می‌کنیم (پلن B)
            if not streams:
                try:
                    import yt_dlp
                    ydl_opts = {
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
                        'listformats': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        for format in info.get('formats', [])[:5]:  # محدود به 5 فرمت اول
                            if format.get('ext') == 'mp4' and format.get('filesize'):
                                resolution = f"{format.get('width', 0)}x{format.get('height', 0)}"
                                filesize = format.get('filesize', 0)
                                if filesize < MAX_TELEGRAM_FILE_SIZE:
                                    key = f"{resolution} ({format_size(filesize)}) - yt-dlp"
                                    streams[key] = (format.get('format_id'), filesize)
                except Exception as e:
                    logger.error(f"خطا در استفاده از yt-dlp: {e}")
            
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
            
            # استخراج شناسه ویدیو برای استفاده احتمالی در روش جایگزین
            video_id = self._get_video_id(url)
            if not video_id:
                logger.error(f"شناسه ویدیو از URL استخراج نشد: {url}")
                return ""
                
            # روش 1: استفاده از pytube
            output_file = ""
            try:
                yt = YouTube(url)
                logger.info(f"اطلاعات ویدیو دریافت شد: {yt.title}")
                
                stream = yt.streams.get_by_itag(itag)
                if not stream:
                    logger.error(f"استریم با شناسه {itag} یافت نشد برای {url}")
                    return ""
                    
                logger.info(f"استریم با کیفیت {stream.resolution} و فرمت {stream.mime_type} یافت شد")
                
                # بررسی سایز فایل
                try:
                    filesize = stream.filesize
                    logger.info(f"سایز فایل: {filesize} بایت ({format_size(filesize)})")
                    if filesize > MAX_TELEGRAM_FILE_SIZE:
                        logger.warning(f"سایز فایل ({format_size(filesize)}) بیشتر از حد مجاز تلگرام است")
                        return ""
                except Exception as size_error:
                    logger.warning(f"خطا در دریافت سایز فایل: {size_error}")
                    # ادامه می‌دهیم حتی اگر سایز را نتوانستیم بررسی کنیم
                
                # تعیین نام فایل خروجی
                output_file = generate_temp_filename('.mp4')
                logger.info(f"نام فایل خروجی: {output_file}")
                
                # دانلود و ذخیره ویدیو
                logger.info("در حال دانلود ویدیو با pytube...")
                stream.download(filename=output_file)
                
                # بررسی وجود فایل
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    file_size = os.path.getsize(output_file)
                    logger.info(f"ویدیو با موفقیت دانلود شد با pytube. سایز فایل: {format_size(file_size)}")
                    return output_file
                else:
                    logger.warning("فایل دانلود شده با pytube خالی است یا ایجاد نشده است")
            except Exception as pytube_error:
                logger.warning(f"خطا در دانلود با pytube: {pytube_error}")
                logger.warning("در حال تلاش با روش جایگزین...")
            
            # روش 2: استفاده از دانلود مستقیم
            if not output_file or not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                logger.info("تلاش برای دانلود با روش مستقیم...")
                direct_output = self._download_via_direct_link(video_id)
                if direct_output:
                    logger.info("دانلود با روش مستقیم موفقیت‌آمیز بود")
                    return direct_output
                else:
                    logger.error("تمام روش‌های دانلود شکست خورد")
                    return ""
            
            return output_file
        
        except Exception as outer_error:
            logger.error(f"خطای کلی در دانلود ویدیو: {outer_error}")
            logger.exception("جزئیات خطا:")
            return ""
    
    def _download_via_direct_link(self, video_id: str) -> str:
        """تلاش برای دانلود مستقیم شورتز با استفاده از API های عمومی"""
        try:
            logger.info(f"تلاش برای دانلود مستقیم ویدیو با شناسه: {video_id}")
            
            # استفاده از سرویس‌های مختلف برای یافتن لینک دانلود
            # روش 1: تلاش با استفاده از yt-dlp API
            try:
                output_file = generate_temp_filename('.mp4')
                logger.info(f"تلاش برای دانلود با استفاده از متد جایگزین... خروجی: {output_file}")
                
                # تلاش با استفاده از اجرای command-line
                import subprocess
                try:
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    logger.info(f"تلاش برای دانلود با استفاده از متد فرعی: {url}")
                    
                    # بررسی آیا pytube نصب شده است و آن را مستقیماً در پایتون استفاده می‌کنیم
                    from pytube import YouTube
                    try:
                        # تلاش مجدد با تنظیمات متفاوت
                        yt = YouTube(url)
                        
                        # دریافت جزئیات ویدیو برای لاگ
                        title = yt.title
                        author = yt.author
                        length = yt.length
                        logger.info(f"اطلاعات ویدیو: عنوان={title}, سازنده={author}, طول={length} ثانیه")
                        
                        # استفاده از تکنیک متفاوت برای دانلود: تلاش با استفاده از adaptive streams
                        video_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by('resolution').desc().first()
                        audio_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_audio=True).order_by('abr').desc().first()
                        
                        if video_stream:
                            logger.info(f"استریم ویدیویی یافت شد: {video_stream.resolution}")
                            video_file = generate_temp_filename('.mp4.video')
                            video_stream.download(filename=video_file)
                            
                            if audio_stream:
                                logger.info(f"استریم صوتی یافت شد: {audio_stream.abr}")
                                audio_file = generate_temp_filename('.mp4.audio')
                                audio_stream.download(filename=audio_file)
                                
                                # ترکیب فایل‌های ویدیو و صدا با FFmpeg
                                if os.path.exists(video_file) and os.path.exists(audio_file):
                                    cmd = [
                                        'ffmpeg', '-i', video_file, '-i', audio_file, 
                                        '-c:v', 'copy', '-c:a', 'aac', '-strict', 'experimental',
                                        output_file, '-y'
                                    ]
                                    try:
                                        subprocess.run(cmd, check=True, capture_output=True)
                                        logger.info("فایل‌های ویدیو و صوتی با موفقیت ترکیب شدند")
                                        os.remove(video_file)
                                        os.remove(audio_file)
                                    except subprocess.CalledProcessError as ffmpeg_error:
                                        logger.error(f"خطا در ترکیب فایل‌های ویدیو و صدا: {ffmpeg_error}")
                                        # استفاده از فایل ویدیو بدون صدا
                                        os.rename(video_file, output_file)
                                        os.remove(audio_file)
                            else:
                                # اگر استریم صوتی پیدا نشد، فقط از ویدیو استفاده می‌کنیم
                                os.rename(video_file, output_file)
                                
                            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                                file_size = os.path.getsize(output_file)
                                logger.info(f"ویدیو با موفقیت دانلود شد. سایز: {format_size(file_size)}")
                                return output_file
                        else:
                            # تلاش با استفاده از progressive streams
                            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                            if stream:
                                logger.info(f"استریم progressive یافت شد: {stream.resolution}")
                                stream.download(filename=output_file)
                                
                                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                                    file_size = os.path.getsize(output_file)
                                    logger.info(f"ویدیو با موفقیت دانلود شد. سایز: {format_size(file_size)}")
                                    return output_file
                    
                    except Exception as pytube_alternative_error:
                        logger.warning(f"خطا در تلاش جایگزین pytube: {pytube_alternative_error}")
                    
                    # اگر به اینجا رسیدیم، روش اول موفق نبوده است
                    # تلاش با استفاده از youtube-dl
                    try:
                        command = ['yt-dlp', '-f', 'best[filesize<50M]', '--merge-output-format', 'mp4', '-o', output_file, url]
                        process = subprocess.run(command, capture_output=True, text=True, check=True)
                        logger.info(f"خروجی yt-dlp: {process.stdout[:200]}")
                        
                        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                            file_size = os.path.getsize(output_file)
                            logger.info(f"ویدیو با موفقیت دانلود شد با yt-dlp. سایز: {format_size(file_size)}")
                            return output_file
                    except subprocess.CalledProcessError as ytdl_error:
                        logger.error(f"خطا در اجرای yt-dlp: {ytdl_error}")
                        
                    # روش جایگزین دیگر: استفاده از youtube-dl
                    try:
                        command = ['youtube-dl', '-f', 'best[filesize<50M]', '--merge-output-format', 'mp4', '-o', output_file, url]
                        process = subprocess.run(command, capture_output=True, text=True, check=True)
                        logger.info(f"خروجی youtube-dl: {process.stdout[:200]}")
                        
                        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                            file_size = os.path.getsize(output_file)
                            logger.info(f"ویدیو با موفقیت دانلود شد با youtube-dl. سایز: {format_size(file_size)}")
                            return output_file
                    except subprocess.CalledProcessError as ytdl_error:
                        logger.error(f"خطا در اجرای youtube-dl: {ytdl_error}")
                
                except ImportError:
                    logger.warning("کتابخانه pytube در دسترس نیست")
                
                except Exception as cmd_error:
                    logger.error(f"خطا در اجرای دستور دانلود: {cmd_error}")
                    logger.exception("جزئیات خطا:")
                    
            except Exception as method_error:
                logger.error(f"خطا در روش اول دانلود: {method_error}")
                logger.exception("جزئیات خطا:")
            
            # روش 2: تلاش برای دانلود مستقیم از API یوتیوب
            try:
                logger.info("تلاش با روش دانلود مستقیم از API یوتیوب...")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Referer': 'https://www.youtube.com/'
                }
                
                # استفاده از یک روش متفاوت برای دانلود شورتز
                # این روش از API اصلی یوتیوب استفاده نمی‌کند، اما ممکن است در برخی موارد کار کند
                url = f"https://vid.puffyan.us/api/v1/videos/{video_id}"
                logger.info(f"تلاش با استفاده از API جایگزین: {url}")
                try:
                    response = requests.get(url, headers=headers)
                    if response.status_code == 200:
                        video_data = response.json()
                        if 'formatStreams' in video_data:
                            best_stream = None
                            for stream in video_data['formatStreams']:
                                if 'url' in stream:
                                    if best_stream is None or ('quality' in stream and '720p' in stream['quality']):
                                        best_stream = stream
                                    if '1080p' in stream.get('quality', ''):
                                        best_stream = stream
                                        break
                            
                            if best_stream and 'url' in best_stream:
                                video_url = best_stream['url']
                                logger.info(f"لینک دانلود مستقیم از API جایگزین یافت شد: {video_url[:50]}...")
                                
                                output_file = generate_temp_filename('.mp4')
                                try:
                                    with requests.get(video_url, stream=True, headers=headers) as r:
                                        r.raise_for_status()
                                        with open(output_file, 'wb') as f:
                                            for chunk in r.iter_content(chunk_size=8192):
                                                f.write(chunk)
                                    
                                    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                                        file_size = os.path.getsize(output_file)
                                        logger.info(f"ویدیو با موفقیت از API جایگزین دانلود شد. سایز: {format_size(file_size)}")
                                        return output_file
                                except Exception as dl_error:
                                    logger.error(f"خطا در دانلود از API جایگزین: {dl_error}")
                except Exception as api_error:
                    logger.error(f"خطا در دریافت داده از API جایگزین: {api_error}")
            
            except Exception as api_method_error:
                logger.error(f"خطا در روش دوم دانلود: {api_method_error}")
                logger.exception("جزئیات خطا:")
            
            # اگر به اینجا رسیدیم، هیچ یک از روش‌ها موفق نبوده است
            logger.error("تمام روش‌های دانلود شکست خورد")
            return ""
                
        except Exception as e:
            logger.error(f"خطای کلی در دانلود مستقیم: {e}")
            logger.exception("جزئیات خطا:")
            return ""
            
        return ""  # اگر همه روش‌ها شکست خورد

    def download_shorts(self, url: str) -> str:
        """دانلود شورتز یوتیوب"""
        try:
            logger.info(f"شروع دانلود شورتز یوتیوب با URL: {url}")
            
            # استخراج شناسه ویدیو
            video_id = self._get_video_id(url)
            if not video_id:
                logger.error(f"شناسه ویدیوی شورتز استخراج نشد: {url}")
                return ""
                
            logger.info(f"شناسه ویدیوی شورتز استخراج شد: {video_id}")
            
            # تبدیل لینک شورتز به لینک عادی ویدیو یوتیوب
            # بعضی وقت‌ها دانلود از لینک شورتز با خطا مواجه می‌شود
            # با این روش، ما از لینک استاندارد استفاده می‌کنیم
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"لینک شورتز به لینک استاندارد تبدیل شد: {watch_url}")
            
            # روش 1: استفاده از pytube
            output_file = ""
            try:
                # سعی اول: استفاده از لینک اصلی
                yt = YouTube(url)
                logger.info(f"اطلاعات شورتز دریافت شد با لینک اصلی: {yt.title}")
                
                # انتخاب بهترین کیفیت موجود برای دانلود
                streams = yt.streams.filter(progressive=True, file_extension='mp4')
                if not streams or len(streams) == 0:
                    # تلاش برای دریافت همه استریم‌ها اگر فیلتر کار نکرد
                    streams = yt.streams.all()
                    logger.info(f"استریم‌های یافت شده (بدون فیلتر): {len(streams)}")
                else:
                    logger.info(f"استریم‌های یافت شده (با فیلتر): {len(streams)}")
                
                stream = None
                try:
                    stream = streams.order_by('resolution').desc().first()
                except:
                    if streams and len(streams) > 0:
                        stream = streams[0]
                
                if stream:
                    # دانلود و ذخیره ویدیو
                    output_file = generate_temp_filename('.mp4')
                    logger.info(f"نام فایل خروجی شورتز: {output_file}")
                    logger.info("در حال دانلود شورتز با pytube...")
                    stream.download(filename=output_file)
                    
                    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                        file_size = os.path.getsize(output_file)
                        logger.info(f"شورتز با موفقیت دانلود شد با pytube. سایز فایل: {format_size(file_size)}")
                        return output_file
                    else:
                        logger.warning("فایل دانلود شده با pytube خالی است یا ایجاد نشده است")
                else:
                    logger.warning("هیچ استریمی برای دانلود با pytube یافت نشد")
            except Exception as pytube_error:
                logger.warning(f"خطا در دانلود با pytube: {pytube_error}")
                logger.warning("در حال تلاش با روش جایگزین...")
            
            # روش 2: استفاده از دانلود مستقیم
            if not output_file or not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                logger.info("تلاش برای دانلود با روش مستقیم...")
                direct_output = self._download_via_direct_link(video_id)
                if direct_output:
                    logger.info("دانلود با روش مستقیم موفقیت‌آمیز بود")
                    return direct_output
                else:
                    logger.error("تمام روش‌های دانلود شکست خورد")
                    return ""
            
            return output_file
        
        except Exception as e:
            logger.error(f"خطای کلی در دانلود شورتز: {e}")
            logger.exception("جزئیات خطا:")
            return ""
    
    def get_playlist_videos(self, playlist_url: str, limit: int = 5) -> List[Dict[str, str]]:
        """دریافت لیست ویدیوهای موجود در پلی‌لیست یوتیوب
        
        Args:
            playlist_url: لینک پلی‌لیست یوتیوب
            limit: حداکثر تعداد ویدیوها (پیش‌فرض: 5)
            
        Returns:
            لیستی از دیکشنری‌ها شامل اطلاعات هر ویدیو (عنوان، URL، و شناسه)
        """
        try:
            logger.info(f"دریافت اطلاعات پلی‌لیست: {playlist_url}")
            
            # تنظیم کردن دستور yt-dlp برای دریافت اطلاعات پلی‌لیست
            from utils import extract_playlist_id
            playlist_id = extract_playlist_id(playlist_url)
            
            if not playlist_id:
                logger.error(f"شناسه پلی‌لیست استخراج نشد: {playlist_url}")
                return []
                
            videos = []
            try:
                # استفاده از yt-dlp برای دریافت اطلاعات پلی‌لیست
                import subprocess
                import json
                
                # ساخت دستور برای دریافت اطلاعات پلی‌لیست با فرمت JSON
                cmd = [
                    'yt-dlp', 
                    '--flat-playlist',  # فقط اطلاعات پلی‌لیست، بدون دانلود
                    '--dump-json',      # خروجی با فرمت JSON
                    f'--playlist-items', f'1-{limit}',  # محدودیت تعداد ویدیوها
                    f'https://www.youtube.com/playlist?list={playlist_id}'
                ]
                
                # اجرای دستور
                process = subprocess.run(cmd, capture_output=True, text=True)
                
                # پردازش خروجی JSON
                if process.stdout:
                    lines = process.stdout.strip().split('\n')
                    
                    for line in lines:
                        if not line.strip():
                            continue
                            
                        try:
                            video_info = json.loads(line)
                            video_id = video_info.get('id')
                            title = video_info.get('title', 'ویدیوی بدون عنوان')
                            
                            if video_id:
                                url = f"https://www.youtube.com/watch?v={video_id}"
                                videos.append({
                                    'id': video_id,
                                    'title': title,
                                    'url': url
                                })
                                logger.info(f"ویدیو پیدا شد: {title}")
                        except json.JSONDecodeError:
                            logger.warning(f"خطا در پردازش JSON ویدیو: {line[:100]}")
            
            except Exception as e:
                logger.error(f"خطا در اجرای yt-dlp: {e}")
                logger.exception("جزئیات خطا:")
                
                # تلاش با روش جایگزین: pytube
                try:
                    from pytube import Playlist
                    
                    playlist = Playlist(playlist_url)
                    logger.info(f"دریافت اطلاعات پلی‌لیست با pytube: {playlist.title}")
                    
                    for i, video_url in enumerate(playlist.video_urls[:limit]):
                        try:
                            yt = YouTube(video_url)
                            video_id = self._get_video_id(video_url)
                            title = yt.title
                            
                            videos.append({
                                'id': video_id,
                                'title': title,
                                'url': video_url
                            })
                            logger.info(f"ویدیو پیدا شد: {title}")
                        except Exception as video_error:
                            logger.warning(f"خطا در دریافت اطلاعات ویدیو {video_url}: {video_error}")
                except Exception as pytube_error:
                    logger.error(f"خطا در دریافت اطلاعات پلی‌لیست با pytube: {pytube_error}")
            
            logger.info(f"تعداد {len(videos)} ویدیو از پلی‌لیست دریافت شد")
            return videos
            
        except Exception as e:
            logger.error(f"خطا در دریافت ویدیوهای پلی‌لیست: {e}")
            logger.exception("جزئیات خطا:")
            return []
    
    def clean_up(self, file_path: str) -> None:
        """پاک کردن فایل موقت"""
        clean_temp_file(file_path)

import logging
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from downloader.instagram import InstagramDownloader
from utils import get_file_size, format_size, convert_video_to_audio, clean_temp_file
from messages import *

# دریافت نمونه logger
logger = logging.getLogger(__name__)

# ایجاد نمونه از کلاس دانلودر اینستاگرام
instagram_downloader = InstagramDownloader()

# دیکشنری برای نگهداری اطلاعات کاربران
user_data = {}

def download_instagram_video(update: Update, context: CallbackContext, url: str, user_id: int) -> None:
    """دانلود ویدیوی اینستاگرام"""
    query = update.callback_query
    query.answer()

    status_message = query.edit_message_text(INSTAGRAM_DOWNLOAD_STARTED)
    downloaded_files = []

    try:
        logger.info(f"شروع دانلود ویدیوی اینستاگرام با URL: {url}")
        downloaded_files = instagram_downloader.download_post(url)

        if not downloaded_files:
            logger.warning(f"هیچ فایلی از {url} دانلود نشد.")
            status_message.edit_text(INSTAGRAM_DOWNLOAD_ERROR)
            return
            
        video_files = [f for f in downloaded_files if not f.endswith('.jpg')]
        
        if not video_files:
            logger.warning(f"هیچ فایل ویدیویی در پست {url} یافت نشد.")
            status_message.edit_text(INSTAGRAM_DOWNLOAD_ERROR)
            return

        logger.info(f"تعداد {len(video_files)} ویدیو از اینستاگرام دانلود شد")
        status_message.edit_text(UPLOAD_TO_TELEGRAM)

        # ارسال ویدیوها به کاربر
        if len(video_files) == 1:
            # اگر فقط یک ویدیو باشد
            file_path = video_files[0]
            file_size = get_file_size(file_path)
            logger.info(f"ارسال ویدیو با سایز {format_size(file_size)}")

            with open(file_path, 'rb') as video_file:
                context.bot.send_video(
                    chat_id=user_data[user_id]['chat_id'],
                    video=video_file,
                    supports_streaming=True
                )
        else:
            # اگر چندین ویدیو باشد (آلبوم ویدیو)
            from telegram import InputMediaVideo
            media_group = []
            for file_path in video_files[:10]:  # حداکثر 10 ویدیو در یک آلبوم
                file_size = get_file_size(file_path)
                logger.info(f"اضافه کردن ویدیو با سایز {format_size(file_size)} به آلبوم")

                with open(file_path, 'rb') as video_file:
                    media_group.append(InputMediaVideo(media=video_file))

            if media_group:
                logger.info(f"ارسال آلبوم با {len(media_group)} ویدیو")
                context.bot.send_media_group(
                    chat_id=user_data[user_id]['chat_id'],
                    media=media_group
                )

        status_message.edit_text(INSTAGRAM_DOWNLOAD_SUCCESS)
        logger.info("ویدیوهای اینستاگرام با موفقیت به کاربر ارسال شد")

    except Exception as e:
        if "No connection" in str(e) or "timeout" in str(e).lower() or "connection" in str(e).lower():
            logger.error(f"خطای شبکه در دانلود ویدیوی اینستاگرام: {e}")
            status_message.edit_text(NETWORK_ERROR)
        elif "rate limit" in str(e).lower() or "too many requests" in str(e).lower():
            logger.error(f"خطای محدودیت در دانلود ویدیوی اینستاگرام: {e}")
            status_message.edit_text(RATE_LIMIT_ERROR)
        else:
            logger.error(f"خطا در دانلود ویدیوی اینستاگرام {url}: {e}")
            logger.exception("جزئیات خطا:")
            status_message.edit_text(INSTAGRAM_DOWNLOAD_ERROR)
    finally:
        # پاک کردن فایل‌های موقت
        if downloaded_files:
            logger.info(f"پاک کردن {len(downloaded_files)} فایل موقت")
            instagram_downloader.clean_up(downloaded_files)
        # پاک کردن اطلاعات کاربر
        if user_id in user_data:
            del user_data[user_id]
            
            
def download_instagram_audio(update: Update, context: CallbackContext, url: str, user_id: int) -> None:
    """دانلود و استخراج صدای ویدیوی اینستاگرام"""
    query = update.callback_query
    query.answer()

    status_message = query.edit_message_text(AUDIO_EXTRACTION_STARTED)
    downloaded_files = []
    audio_file = ""

    try:
        logger.info(f"شروع دانلود ویدیوی اینستاگرام برای استخراج صدا با URL: {url}")
        # ابتدا ویدیو را دانلود می‌کنیم
        downloaded_files = instagram_downloader.download_post(url)

        if not downloaded_files:
            logger.warning(f"هیچ فایلی از {url} دانلود نشد.")
            status_message.edit_text(INSTAGRAM_DOWNLOAD_ERROR)
            return

        # فقط فایل‌های ویدیویی را استخراج می‌کنیم
        video_files = [f for f in downloaded_files if not f.endswith('.jpg')]
        
        if not video_files:
            logger.warning(f"هیچ فایل ویدیویی در پست {url} یافت نشد.")
            status_message.edit_text(INSTAGRAM_DOWNLOAD_ERROR)
            return
            
        logger.info(f"تعداد {len(video_files)} ویدیو از اینستاگرام دانلود شد")
        
        # اگر چندین ویدیو باشد، فقط از اولین ویدیو صدا استخراج می‌کنیم
        video_file = video_files[0]

        # استخراج صدا از ویدیو
        logger.info("در حال استخراج صدا از ویدیو...")
        audio_file = convert_video_to_audio(video_file)

        if not audio_file:
            logger.error("خطا در استخراج صدا از ویدیو")
            status_message.edit_text(AUDIO_EXTRACTION_ERROR)
            return

        file_size = get_file_size(audio_file)
        logger.info(f"صدا با موفقیت استخراج شد. سایز: {format_size(file_size)}")

        status_message.edit_text(UPLOAD_TO_TELEGRAM)

        # ارسال فایل صوتی به کاربر
        with open(audio_file, 'rb') as audio:
            context.bot.send_audio(
                chat_id=user_data[user_id]['chat_id'],
                audio=audio,
                title=f"Audio from Instagram"
            )

        status_message.edit_text(AUDIO_EXTRACTION_SUCCESS)
        logger.info("فایل صوتی با موفقیت به کاربر ارسال شد")

    except Exception as e:
        logger.error(f"خطا در استخراج صدا از ویدیوی اینستاگرام {url}: {e}")
        logger.exception("جزئیات خطا:")
        status_message.edit_text(AUDIO_EXTRACTION_ERROR)
    finally:
        # پاک کردن فایل‌های موقت
        if downloaded_files:
            logger.info(f"پاک کردن {len(downloaded_files)} فایل موقت")
            instagram_downloader.clean_up(downloaded_files)
        if audio_file:
            logger.info(f"پاک کردن فایل موقت صوتی: {audio_file}")
            clean_temp_file(audio_file)
        # پاک کردن اطلاعات کاربر
        if user_id in user_data:
            del user_data[user_id]
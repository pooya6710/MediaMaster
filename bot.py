import os
import re
import logging
from typing import Dict, List, Optional, Tuple, Any

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    Updater,
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    Filters, 
    CallbackContext
)
from instaloader.exceptions import PrivateProfileNotFollowedException

from config import TOKEN, logger
from messages import *
from utils import (
    extract_url, 
    is_instagram_url, 
    is_youtube_url, 
    is_youtube_shorts, 
    get_file_size,
    format_size,
    clean_temp_file
)
from downloader.instagram import InstagramDownloader
from downloader.youtube import YouTubeDownloader

# راه‌اندازی دانلودرها
instagram_downloader = InstagramDownloader()
youtube_downloader = YouTubeDownloader()

# دیکشنری برای نگهداری اطلاعات موقت کاربران
user_data = {}

def start(update: Update, context: CallbackContext) -> None:
    """پاسخ به دستور /start"""
    update.message.reply_text(START_MESSAGE, parse_mode='Markdown')

def help_command(update: Update, context: CallbackContext) -> None:
    """پاسخ به دستور /help"""
    update.message.reply_text(HELP_MESSAGE, parse_mode='Markdown')

def about_command(update: Update, context: CallbackContext) -> None:
    """پاسخ به دستور /about"""
    update.message.reply_text(ABOUT_MESSAGE, parse_mode='Markdown')

def process_message(update: Update, context: CallbackContext) -> None:
    """پردازش پیام‌های ورودی و استخراج لینک"""
    if not update.message or not update.message.text:
        return
    
    logger.info(f"پردازش پیام: {update.message.text[:50]}...")
    
    # بهبود شناسایی لینک‌های یوتیوب شورتز
    original_text = update.message.text
    user_id = update.effective_user.id
    
    # برای لینک‌های خاص YouTube Shorts
    if "youtube.com/shorts/" in original_text:
        shorts_pattern = r'(https?://(?:www\.)?youtube\.com/shorts/[\w-]+)'
        shorts_match = re.search(shorts_pattern, original_text)
        if shorts_match:
            shorts_url = shorts_match.group(1)
            logger.info(f"لینک شورتز یوتیوب به طور مستقیم شناسایی شد: {shorts_url}")
            process_youtube_shorts(update, context, shorts_url, user_id)
            return
    
    # برای لینک‌های عادی یوتیوب
    if "youtube.com/watch?v=" in original_text:
        video_pattern = r'(https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+(?:&\S*)?)'
        video_match = re.search(video_pattern, original_text)
        if video_match:
            video_url = video_match.group(1)
            logger.info(f"لینک ویدیوی یوتیوب به طور مستقیم شناسایی شد: {video_url}")
            process_youtube_video(update, context, video_url, user_id)
            return
            
    # برای لینک‌های کوتاه یوتیوب
    if "youtu.be/" in original_text:
        short_url_pattern = r'(https?://(?:www\.)?youtu\.be/[\w-]+)'
        short_url_match = re.search(short_url_pattern, original_text)
        if short_url_match:
            short_url = short_url_match.group(1)
            logger.info(f"لینک کوتاه یوتیوب به طور مستقیم شناسایی شد: {short_url}")
            process_youtube_video(update, context, short_url, user_id)
            return
    
    # برای لینک‌های اینستاگرام
    if "instagram.com/" in original_text:
        instagram_pattern = r'(https?://(?:www\.)?instagram\.com/\S+)'
        instagram_match = re.search(instagram_pattern, original_text)
        if instagram_match:
            instagram_url = instagram_match.group(1)
            logger.info(f"لینک اینستاگرام به طور مستقیم شناسایی شد: {instagram_url}")
            process_instagram_url(update, context, instagram_url, user_id)
            return
    
    # اگر شناسایی مستقیم موفق نبود، از روش عمومی استفاده می‌کنیم
    url = extract_url(original_text)
    if not url:
        logger.warning(f"لینک معتبری یافت نشد در پیام: {original_text[:50]}...")
        update.message.reply_text(NO_LINK_FOUND)
        return
    
    logger.info(f"URL استخراج شده با روش عمومی: {url} - کاربر: {user_id}")
    
    if is_instagram_url(url):
        logger.info(f"پردازش لینک اینستاگرام: {url}")
        process_instagram_url(update, context, url, user_id)
    elif is_youtube_url(url):
        logger.info(f"پردازش لینک یوتیوب: {url}")
        process_youtube_url(update, context, url, user_id)
    else:
        logger.warning(f"لینک پشتیبانی نشده: {url}")
        update.message.reply_text(UNSUPPORTED_LINK)

def process_instagram_url(update: Update, context: CallbackContext, url: str, user_id: int) -> None:
    """پردازش لینک اینستاگرام"""
    status_message = update.message.reply_text(INSTAGRAM_DOWNLOAD_STARTED)
    downloaded_files = []  # تعریف لیست خالی برای فایل‌های دانلود شده
    
    try:
        logger.info(f"شروع دانلود محتوا از اینستاگرام با URL: {url}")
        downloaded_files = instagram_downloader.download_post(url)
        
        if not downloaded_files:
            logger.warning(f"هیچ فایلی از {url} دانلود نشد.")
            status_message.edit_text(INSTAGRAM_DOWNLOAD_ERROR)
            return
        
        logger.info(f"تعداد {len(downloaded_files)} فایل از اینستاگرام دانلود شد")
        status_message.edit_text(UPLOAD_TO_TELEGRAM)
        
        # ارسال فایل‌ها به کاربر
        if len(downloaded_files) == 1:
            # اگر فقط یک فایل باشد
            file_path = downloaded_files[0]
            file_size = get_file_size(file_path)
            logger.info(f"ارسال فایل با سایز {format_size(file_size)}")
            
            try:
                if file_path.endswith('.jpg'):
                    with open(file_path, 'rb') as photo_file:
                        update.message.reply_photo(photo=photo_file)
                else:
                    with open(file_path, 'rb') as video_file:
                        update.message.reply_video(video=video_file)
            except Exception as send_error:
                logger.error(f"خطا در ارسال فایل به کاربر: {send_error}")
                status_message.edit_text(GENERAL_ERROR)
                return
                
        else:
            # اگر چندین فایل باشد (آلبوم)
            media_group = []
            try:
                for file_path in downloaded_files[:10]:  # حداکثر 10 فایل در یک آلبوم
                    file_size = get_file_size(file_path)
                    logger.info(f"اضافه کردن فایل با سایز {format_size(file_size)} به آلبوم")
                    
                    with open(file_path, 'rb') as media_file:
                        if file_path.endswith('.jpg'):
                            media_group.append(InputMediaPhoto(media=media_file))
                        else:
                            media_group.append(InputMediaVideo(media=media_file))
                
                if media_group:
                    logger.info(f"ارسال آلبوم با {len(media_group)} فایل")
                    update.message.reply_media_group(media=media_group)
                    
            except Exception as album_error:
                logger.error(f"خطا در ارسال آلبوم به کاربر: {album_error}")
                status_message.edit_text(GENERAL_ERROR)
                return
        
        status_message.edit_text(INSTAGRAM_DOWNLOAD_SUCCESS)
        logger.info("محتوا با موفقیت به کاربر ارسال شد")
    
    except PrivateProfileNotFollowedException:
        logger.warning(f"پروفایل خصوصی: {url}")
        status_message.edit_text(INSTAGRAM_PRIVATE_ACCOUNT)
    except Exception as e:
        if "No connection" in str(e) or "timeout" in str(e).lower() or "connection" in str(e).lower():
            logger.error(f"خطای شبکه در دانلود از اینستاگرام: {e}")
            status_message.edit_text(NETWORK_ERROR)
        elif "rate limit" in str(e).lower() or "too many requests" in str(e).lower():
            logger.error(f"خطای محدودیت در دانلود از اینستاگرام: {e}")
            status_message.edit_text(RATE_LIMIT_ERROR)
        else:
            logger.error(f"خطا در پردازش لینک اینستاگرام {url}: {e}")
            logger.exception("جزئیات خطا:")
            status_message.edit_text(INSTAGRAM_DOWNLOAD_ERROR)
    finally:
        # پاک کردن فایل‌های موقت
        if downloaded_files:
            logger.info(f"پاک کردن {len(downloaded_files)} فایل موقت")
            instagram_downloader.clean_up(downloaded_files)

def process_youtube_url(update: Update, context: CallbackContext, url: str, user_id: int) -> None:
    """پردازش لینک یوتیوب"""
    if is_youtube_shorts(url):
        process_youtube_shorts(update, context, url, user_id)
    else:
        process_youtube_video(update, context, url, user_id)

def process_youtube_shorts(update: Update, context: CallbackContext, url: str, user_id: int) -> None:
    """پردازش لینک شورتز یوتیوب"""
    status_message = update.message.reply_text(YOUTUBE_SHORTS_DOWNLOAD_STARTED)
    output_file = ""  # تعریف متغیر خروجی
    
    try:
        logger.info(f"شروع دانلود شورتز یوتیوب با URL: {url}")
        output_file = youtube_downloader.download_shorts(url)
        
        if not output_file:
            logger.warning(f"هیچ فایلی از شورتز {url} دانلود نشد.")
            status_message.edit_text(YOUTUBE_DOWNLOAD_ERROR)
            return
        
        logger.info(f"شورتز یوتیوب با موفقیت دانلود شد: {output_file}")
        file_size = get_file_size(output_file)
        logger.info(f"سایز فایل شورتز: {format_size(file_size)}")
        
        status_message.edit_text(UPLOAD_TO_TELEGRAM)
        
        # ارسال ویدیو به کاربر
        try:
            with open(output_file, 'rb') as video_file:
                update.message.reply_video(video=video_file)
            
            status_message.edit_text(YOUTUBE_SHORTS_DOWNLOAD_SUCCESS)
            logger.info("شورتز یوتیوب با موفقیت به کاربر ارسال شد")
            
        except Exception as send_error:
            logger.error(f"خطا در ارسال شورتز به کاربر: {send_error}")
            status_message.edit_text(GENERAL_ERROR)
    
    except Exception as e:
        if "No connection" in str(e) or "timeout" in str(e).lower() or "connection" in str(e).lower():
            logger.error(f"خطای شبکه در دانلود شورتز یوتیوب: {e}")
            status_message.edit_text(NETWORK_ERROR)
        elif "rate limit" in str(e).lower() or "too many requests" in str(e).lower():
            logger.error(f"خطای محدودیت در دانلود شورتز یوتیوب: {e}")
            status_message.edit_text(RATE_LIMIT_ERROR)
        else:
            logger.error(f"خطا در پردازش شورتز یوتیوب {url}: {e}")
            logger.exception("جزئیات خطا:")
            status_message.edit_text(YOUTUBE_DOWNLOAD_ERROR)
    finally:
        # پاک کردن فایل موقت
        if output_file:
            logger.info(f"پاک کردن فایل موقت شورتز: {output_file}")
            youtube_downloader.clean_up(output_file)

def process_youtube_video(update: Update, context: CallbackContext, url: str, user_id: int) -> None:
    """پردازش لینک ویدیوی یوتیوب"""
    status_message = update.message.reply_text(YOUTUBE_DOWNLOAD_STARTED)
    
    try:
        # دریافت استریم‌های موجود
        streams = youtube_downloader.get_available_streams(url)
        
        if not streams:
            status_message.edit_text(YOUTUBE_DOWNLOAD_ERROR)
            return
        
        # ذخیره اطلاعات برای استفاده در کالبک
        user_data[user_id] = {
            'youtube_url': url,
            'streams': streams,
            'status_message_id': status_message.message_id,
            'chat_id': update.effective_chat.id
        }
        
        # ایجاد دکمه‌های انتخاب کیفیت
        keyboard = []
        for resolution, (itag, _) in streams.items():
            keyboard.append([InlineKeyboardButton(resolution, callback_data=f"yt_{itag}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status_message.edit_text(
            YOUTUBE_QUALITY_SELECTION,
            reply_markup=reply_markup
        )
    
    except Exception as e:
        logger.error(f"خطا در پردازش ویدیوی یوتیوب {url}: {e}")
        status_message.edit_text(YOUTUBE_DOWNLOAD_ERROR)

def youtube_button_callback(update: Update, context: CallbackContext) -> None:
    """پردازش انتخاب کیفیت ویدیوی یوتیوب"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    if user_id not in user_data:
        logger.warning(f"کاربر {user_id} در دیکشنری داده‌ها یافت نشد")
        query.edit_message_text(GENERAL_ERROR)
        return
    
    # استخراج شناسه استریم از کالبک
    itag = int(query.data.split('_')[1])
    url = user_data[user_id]['youtube_url']
    logger.info(f"دانلود ویدیوی یوتیوب با itag: {itag} - URL: {url}")
    
    query.edit_message_text(DOWNLOADING_MESSAGE)
    output_file = ""  # تعریف متغیر خروجی
    
    try:
        # دانلود ویدیو با کیفیت انتخاب شده
        output_file = youtube_downloader.download_video(url, itag)
        
        if not output_file:
            logger.warning(f"هیچ فایلی با itag {itag} از URL {url} دانلود نشد")
            query.edit_message_text(YOUTUBE_DOWNLOAD_ERROR)
            return
        
        logger.info(f"ویدیوی یوتیوب با موفقیت دانلود شد: {output_file}")
        file_size = get_file_size(output_file)
        logger.info(f"سایز فایل ویدیو: {format_size(file_size)}")
        
        # ارسال ویدیو به کاربر
        query.edit_message_text(UPLOAD_TO_TELEGRAM)
        
        try:
            with open(output_file, 'rb') as video_file:
                context.bot.send_video(
                    chat_id=user_data[user_id]['chat_id'],
                    video=video_file,
                    supports_streaming=True
                )
            
            logger.info("ویدیوی یوتیوب با موفقیت به کاربر ارسال شد")
            query.edit_message_text(YOUTUBE_DOWNLOAD_SUCCESS)
        
        except Exception as send_error:
            logger.error(f"خطا در ارسال ویدیوی یوتیوب به کاربر: {send_error}")
            query.edit_message_text(GENERAL_ERROR)
    
    except Exception as e:
        if "No connection" in str(e) or "timeout" in str(e).lower() or "connection" in str(e).lower():
            logger.error(f"خطای شبکه در دانلود ویدیوی یوتیوب: {e}")
            query.edit_message_text(NETWORK_ERROR)
        elif "rate limit" in str(e).lower() or "too many requests" in str(e).lower():
            logger.error(f"خطای محدودیت در دانلود ویدیوی یوتیوب: {e}")
            query.edit_message_text(RATE_LIMIT_ERROR)
        else:
            logger.error(f"خطا در دانلود ویدیوی یوتیوب: {e}")
            logger.exception("جزئیات خطا:")
            query.edit_message_text(YOUTUBE_DOWNLOAD_ERROR)
    finally:
        # پاک کردن اطلاعات کاربر و فایل موقت
        if user_id in user_data:
            logger.info(f"پاک کردن اطلاعات کاربر {user_id} از دیکشنری")
            del user_data[user_id]
        if output_file:
            logger.info(f"پاک کردن فایل موقت ویدیو: {output_file}")
            youtube_downloader.clean_up(output_file)

def main() -> None:
    """راه‌اندازی بات"""
    # ایجاد آپدیتر
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher
    
    # اضافه کردن هندلرها
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("about", about_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, process_message))
    dispatcher.add_handler(CallbackQueryHandler(youtube_button_callback, pattern="^yt_"))
    
    # شروع بات
    logger.info("بات در حال اجرا است...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

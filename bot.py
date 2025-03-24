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
    
    url = extract_url(update.message.text)
    if not url:
        update.message.reply_text(UNSUPPORTED_LINK)
        return
    
    user_id = update.effective_user.id
    
    if is_instagram_url(url):
        process_instagram_url(update, context, url, user_id)
    elif is_youtube_url(url):
        process_youtube_url(update, context, url, user_id)
    else:
        update.message.reply_text(UNSUPPORTED_LINK)

def process_instagram_url(update: Update, context: CallbackContext, url: str, user_id: int) -> None:
    """پردازش لینک اینستاگرام"""
    status_message = update.message.reply_text(INSTAGRAM_DOWNLOAD_STARTED)
    
    try:
        downloaded_files = instagram_downloader.download_post(url)
        
        if not downloaded_files:
            status_message.edit_text(INSTAGRAM_DOWNLOAD_ERROR)
            return
        
        status_message.edit_text(UPLOAD_TO_TELEGRAM)
        
        # ارسال فایل‌ها به کاربر
        if len(downloaded_files) == 1:
            # اگر فقط یک فایل باشد
            file_path = downloaded_files[0]
            if file_path.endswith('.jpg'):
                update.message.reply_photo(photo=open(file_path, 'rb'))
            else:
                update.message.reply_video(video=open(file_path, 'rb'))
        else:
            # اگر چندین فایل باشد (آلبوم)
            media_group = []
            for file_path in downloaded_files[:10]:  # حداکثر 10 فایل در یک آلبوم
                if file_path.endswith('.jpg'):
                    media_group.append(InputMediaPhoto(media=open(file_path, 'rb')))
                else:
                    media_group.append(InputMediaVideo(media=open(file_path, 'rb')))
            
            if media_group:
                update.message.reply_media_group(media=media_group)
        
        status_message.edit_text(INSTAGRAM_DOWNLOAD_SUCCESS)
    
    except PrivateProfileNotFollowedException:
        status_message.edit_text(INSTAGRAM_PRIVATE_ACCOUNT)
    except Exception as e:
        logger.error(f"خطا در پردازش لینک اینستاگرام {url}: {e}")
        status_message.edit_text(INSTAGRAM_DOWNLOAD_ERROR)
    finally:
        # پاک کردن فایل‌های موقت
        if 'downloaded_files' in locals() and downloaded_files:
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
    
    try:
        output_file = youtube_downloader.download_shorts(url)
        
        if not output_file:
            status_message.edit_text(YOUTUBE_DOWNLOAD_ERROR)
            return
        
        status_message.edit_text(UPLOAD_TO_TELEGRAM)
        
        # ارسال ویدیو به کاربر
        with open(output_file, 'rb') as video_file:
            update.message.reply_video(video=video_file)
        
        status_message.edit_text(YOUTUBE_SHORTS_DOWNLOAD_SUCCESS)
    
    except Exception as e:
        logger.error(f"خطا در پردازش شورتز یوتیوب {url}: {e}")
        status_message.edit_text(YOUTUBE_DOWNLOAD_ERROR)
    finally:
        # پاک کردن فایل موقت
        if 'output_file' in locals() and output_file:
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
        query.edit_message_text(GENERAL_ERROR)
        return
    
    # استخراج شناسه استریم از کالبک
    itag = int(query.data.split('_')[1])
    url = user_data[user_id]['youtube_url']
    
    query.edit_message_text(DOWNLOADING_MESSAGE)
    
    try:
        # دانلود ویدیو با کیفیت انتخاب شده
        output_file = youtube_downloader.download_video(url, itag)
        
        if not output_file:
            query.edit_message_text(YOUTUBE_DOWNLOAD_ERROR)
            return
        
        # ارسال ویدیو به کاربر
        query.edit_message_text(UPLOAD_TO_TELEGRAM)
        
        with open(output_file, 'rb') as video_file:
            context.bot.send_video(
                chat_id=user_data[user_id]['chat_id'],
                video=video_file,
                supports_streaming=True
            )
        
        query.edit_message_text(YOUTUBE_DOWNLOAD_SUCCESS)
    
    except Exception as e:
        logger.error(f"خطا در دانلود ویدیوی یوتیوب: {e}")
        query.edit_message_text(YOUTUBE_DOWNLOAD_ERROR)
    finally:
        # پاک کردن اطلاعات کاربر و فایل موقت
        if user_id in user_data:
            del user_data[user_id]
        if 'output_file' in locals() and output_file:
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

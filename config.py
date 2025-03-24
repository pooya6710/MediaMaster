import os
import logging

# تنظیمات لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن بات تلگرام
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    logger.error("توکن بات تلگرام پیدا نشد! لطفا متغیر محیطی TELEGRAM_BOT_TOKEN را تنظیم کنید.")
    exit(1)

# حداکثر اندازه فایل قابل آپلود در تلگرام (50 مگابایت)
MAX_TELEGRAM_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# مسیر موقت برای ذخیره فایل‌ها
TEMP_DOWNLOAD_DIR = "./downloads"

# ایجاد مسیر دانلود موقت اگر وجود نداشته باشد
if not os.path.exists(TEMP_DOWNLOAD_DIR):
    os.makedirs(TEMP_DOWNLOAD_DIR)

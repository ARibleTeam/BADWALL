import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

# Порог вероятности мата для удаления сообщения. рекомендуется 0.7
PROFANITY_THRESHOLD = os.getenv("PROFANITY_THRESHOLD")
if not PROFANITY_THRESHOLD:
    raise ValueError("PROFANITY_THRESHOLD не найден в переменных окружения!")
PROFANITY_THRESHOLD = float(PROFANITY_THRESHOLD)

# Список разрешенных чатов (chat_id через запятую)
ALLOWED_CHAT_IDS_STR = os.getenv("ALLOWED_CHAT_IDS", "")
if not ALLOWED_CHAT_IDS_STR:
    raise ValueError("ALLOWED_CHAT_IDS не найден в переменных окружения! Укажите chat_id чатов через запятую.")

# Парсим список разрешенных чатов
ALLOWED_CHAT_IDS = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_STR.split(",") if chat_id.strip()]
if not ALLOWED_CHAT_IDS:
    raise ValueError("ALLOWED_CHAT_IDS пуст! Укажите хотя бы один chat_id.")

# Список ID чата и канала, от которых сообщения не модерируются (sender_chat.id через запятую).
# Например: канал, привязанный к группе, и ID самой группы для постов «от имени группы».
EXEMPT_SENDER_CHAT_IDS_STR = os.getenv("EXEMPT_SENDER_CHAT_IDS", "")
EXEMPT_SENDER_CHAT_IDS = [int(x.strip()) for x in EXEMPT_SENDER_CHAT_IDS_STR.split(",") if x.strip()]

# Список админов для получения статистики (user_id через запятую)
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
if not ADMIN_IDS_STR:
    raise ValueError("ADMIN_IDS не найден в переменных окружения! Укажите user_id админов через запятую.")

# Парсим список админов
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(",") if admin_id.strip()]
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS пуст! Укажите хотя бы один user_id админа.")

# Время отправки статистики (часы:минуты)
STATS_TIME = "21:00"

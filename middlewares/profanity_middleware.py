import logging
from typing import Any, Awaitable, Callable, Dict, Optional
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from aiogram.enums import ChatType
from check_swear import SwearingCheck
from config import PROFANITY_THRESHOLD, ALLOWED_CHAT_IDS
from utils.statistics import Statistics

logger = logging.getLogger(__name__)


class ProfanityMiddleware(BaseMiddleware):
    """Middleware для проверки сообщений на наличие мата"""
    
    def __init__(self, statistics: Optional[Statistics] = None):
        super().__init__()
        self.swear_checker = SwearingCheck()
        self.statistics = statistics
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем только сообщения
        if isinstance(event, Message):
            chat_id = event.chat.id
            chat_type = event.chat.type
            
            # Личные сообщения пропускаем без проверки (модерация только для групп)
            if chat_type == ChatType.PRIVATE:
                return await handler(event, data)
            
            # Для групповых чатов проверяем разрешенные чаты
            if chat_id not in ALLOWED_CHAT_IDS:
                # Игнорируем сообщения из неразрешенных чатов
                return
            
            # Проверяем только текстовые сообщения
            if event.text:
                # Собираем статистику
                if self.statistics:
                    self.statistics.add_checked(chat_id)
                
                # Получаем информацию об отправителе для логирования
                sender_id = event.from_user.id if event.from_user else None
                sender_name = event.from_user.username if event.from_user and event.from_user.username else (
                    event.from_user.first_name if event.from_user and event.from_user.first_name else "Unknown"
                )
                chat_title = event.chat.title if hasattr(event.chat, 'title') and event.chat.title else f"Chat {chat_id}"
                
                # Получаем вероятность наличия мата
                # predict_proba возвращает список вероятностей
                proba = self.swear_checker.predict_proba(event.text)
                
                # Для одной строки возвращается список с одним float элементом
                # Берем максимальную вероятность из списка
                if isinstance(proba, list):
                    max_proba = max(proba)
                else:
                    max_proba = float(proba)
                
                # Если вероятность мата превышает порог - удаляем сообщение
                if max_proba >= PROFANITY_THRESHOLD:
                    try:
                        await event.delete()
                        # Собираем статистику об удалении
                        if self.statistics:
                            self.statistics.add_deleted(chat_id)
                        
                        # Логируем удаление
                        logger.info(
                            f"🗑️ УДАЛЕНО | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id}) | "
                            f"Probability: {max_proba:.3f} (threshold: {PROFANITY_THRESHOLD}) | "
                            f"Text: {event.text[:100]}{'...' if len(event.text) > 100 else ''}"
                        )
                    except Exception as e:
                        # Если не удалось удалить (например, нет прав), просто пропускаем
                        logger.error(
                            f"❌ ОШИБКА УДАЛЕНИЯ | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id}) | "
                            f"Probability: {max_proba:.3f} | Error: {e} | "
                            f"Text: {event.text[:100]}{'...' if len(event.text) > 100 else ''}"
                        )
                    # Не вызываем handler, чтобы сообщение не обрабатывалось дальше
                    return
                else:
                    # Логируем, что сообщение оставлено
                    logger.info(
                        f"✅ ОСТАВЛЕНО | Chat: {chat_title} ({chat_id}) | "
                        f"User: {sender_name} (ID: {sender_id}) | "
                        f"Probability: {max_proba:.3f} (threshold: {PROFANITY_THRESHOLD}) | "
                        f"Text: {event.text[:100]}{'...' if len(event.text) > 100 else ''}"
                    )
        
        # Если проверка пройдена или это не текстовое сообщение - продолжаем обработку
        return await handler(event, data)


from typing import Any, Awaitable, Callable, Dict, Optional
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from aiogram.enums import ChatType
from check_swear import SwearingCheck
from config import PROFANITY_THRESHOLD, ALLOWED_CHAT_IDS
from utils.statistics import Statistics


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
                    except Exception as e:
                        # Если не удалось удалить (например, нет прав), просто пропускаем
                        print(f"Не удалось удалить сообщение: {e}")
                    # Не вызываем handler, чтобы сообщение не обрабатывалось дальше
                    return
        
        # Если проверка пройдена или это не текстовое сообщение - продолжаем обработку
        return await handler(event, data)


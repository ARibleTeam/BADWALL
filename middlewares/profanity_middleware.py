import logging
import re
from typing import Any, Awaitable, Callable, Dict, Optional
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, TelegramObject, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType, ChatMemberStatus, MessageEntityType
from check_swear import SwearingCheck
from config import PROFANITY_THRESHOLD, ALLOWED_CHAT_IDS, ADMIN_IDS
from utils.statistics import Statistics

logger = logging.getLogger(__name__)


class ProfanityMiddleware(BaseMiddleware):
    """Middleware для проверки сообщений на наличие мата и ссылок"""
    
    def __init__(self, statistics: Optional[Statistics] = None):
        super().__init__()
        self.swear_checker = SwearingCheck()
        self.statistics = statistics
        # Регулярное выражение для поиска URL
        self.url_pattern = re.compile(
            r'(?i)\b(?:https?://|www\.|t\.me/|telegram\.me/)'
            r'[^\s<>"{}|\\^`\[\]]+',
            re.IGNORECASE
        )
        # Паттерн для поиска запрещенных спецсимволов (исключая разрешенные знаки препинания)
        # Запрещенные: @ # $ % ^ & * + = | \ / < > ~ ` и другие
        # Разрешенные знаки препинания: . , ! ? : ; - ( ) [ ] { } " ' « » — … и пробелы
        self.forbidden_special_chars_pattern = re.compile(
            r'[@#$%^&*+=|\\/<>~`]',
            re.UNICODE
        )
    
    def _has_urls(self, message: Message) -> bool:
        """Проверяет наличие ссылок в сообщении"""
        # Проверяем entities на наличие URL
        if message.entities:
            for entity in message.entities:
                if entity.type in (MessageEntityType.URL, MessageEntityType.TEXT_LINK):
                    return True
        
        # Проверяем caption entities (для сообщений с медиа)
        if message.caption_entities:
            for entity in message.caption_entities:
                if entity.type in (MessageEntityType.URL, MessageEntityType.TEXT_LINK):
                    return True
        
        # Проверяем текст на наличие URL регулярным выражением
        text_to_check = message.text or message.caption or ""
        if text_to_check and self.url_pattern.search(text_to_check):
            return True
        
        return False
    
    def _has_forbidden_chars(self, text: str) -> bool:
        """Проверяет наличие запрещенных символов: спецсимволов (кроме знаков препинания) и нерусских букв"""
        if not text:
            return False
        
        # Проверяем наличие латиницы (a-zA-Z) - это точно нерусские буквы
        if re.search(r'[a-zA-Z]', text):
            return True
        
        # Проверяем наличие запрещенных спецсимволов
        if self.forbidden_special_chars_pattern.search(text):
            return True
        
        # Проверяем наличие других нерусских букв (кириллица других языков, иероглифы и т.д.)
        # Разрешаем только русские буквы (а-я, А-Я, ё, Ё), цифры, пробелы и знаки препинания
        # Если символ не входит в разрешенный набор - это запрещенный символ
        for char in text:
            # Пропускаем русские буквы
            if '\u0400' <= char <= '\u04FF' or char == '\u0451' or char == '\u0401':  # Кириллица и ё, Ё
                continue
            # Пропускаем цифры
            if char.isdigit():
                continue
            # Пропускаем пробелы и разрешенные знаки препинания
            if char in ' .,!?:;-()[]{}"\'«»—…':
                continue
            # Если дошли сюда - это запрещенный символ
            return True
        
        return False
    
    async def _send_ban_notification(
        self,
        bot: Bot,
        chat_id: int,
        chat_title: str,
        user_id: int,
        username: Optional[str],
        first_name: str,
        message_text: str,
        probability: float
    ):
        """Отправляет уведомление админам о бане пользователя"""
        try:
            # Формируем текст уведомления
            notification_text = (
                f"🔨 <b>Пользователь забанен</b>\n\n"
                f"👤 <b>Пользователь:</b> {first_name}"
            )
            
            if username:
                notification_text += f" (@{username})"
            
            notification_text += f"\n🆔 <b>ID:</b> <code>{user_id}</code>\n"
            notification_text += f"💬 <b>Чат:</b> {chat_title}\n"
            notification_text += f"🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n\n"
            notification_text += f"📊 <b>Причина:</b> Мат (вероятность: {probability:.3f})\n\n"
            notification_text += f"💬 <b>Сообщение:</b>\n<code>{message_text[:500]}{'...' if len(message_text) > 500 else ''}</code>"
            
            # Создаем инлайн клавиатуру
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Разбанить",
                        callback_data=f"unban_{chat_id}_{user_id}"
                    ),
                    InlineKeyboardButton(
                        text="🗑️ Скрыть",
                        callback_data="hide_ban_notification"
                    )
                ]
            ])
            
            # Отправляем уведомление всем админам
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=notification_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    logger.info(f"Уведомление о бане отправлено админу {admin_id}")
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о бане: {e}")
    
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
            
            # Проверяем текстовые сообщения и сообщения с подписями
            if event.text or event.caption:
                # Получаем информацию об отправителе
                sender_id = event.from_user.id if event.from_user else None
                sender_name = event.from_user.username if event.from_user and event.from_user.username else (
                    event.from_user.first_name if event.from_user and event.from_user.first_name else "Unknown"
                )
                chat_title = event.chat.title if hasattr(event.chat, 'title') and event.chat.title else f"Chat {chat_id}"
                
                # Проверяем, является ли пользователь администратором или создателем чата
                # Если да - пропускаем проверку на мат и ссылки
                if sender_id:
                    try:
                        # Получаем объект бота из data (в aiogram 3.x бот всегда доступен через data)
                        bot: Bot = data.get("bot")
                        if bot:
                            chat_member = await bot.get_chat_member(chat_id, sender_id)
                            # Пропускаем проверку для создателя и администраторов
                            if chat_member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR):
                                logger.debug(
                                    f"⏭️ ПРОПУЩЕНО (админ) | Chat: {chat_title} ({chat_id}) | "
                                    f"User: {sender_name} (ID: {sender_id}) | Status: {chat_member.status.value}"
                                )
                                # Пропускаем проверку для администраторов
                                return await handler(event, data)
                    except Exception as e:
                        # Если не удалось проверить статус (например, бот не админ), продолжаем проверку
                        logger.warning(
                            f"⚠️ Не удалось проверить статус пользователя {sender_id} в чате {chat_id}: {e}. "
                            f"Продолжаем проверку сообщения."
                        )
                
                # Получаем текст сообщения для проверок
                message_text = event.text or event.caption or ""
                
                # Проверяем наличие запрещенных символов (спецсимволы и нерусские буквы)
                if self._has_forbidden_chars(message_text):
                    try:
                        await event.delete()
                        # Собираем статистику об удалении
                        if self.statistics:
                            self.statistics.add_checked(chat_id)
                            self.statistics.add_deleted(chat_id, deletion_type="forbidden_chars")
                        
                        # Логируем удаление
                        logger.info(
                            f"🚫 УДАЛЕНО (запрещенные символы) | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id}) | "
                            f"Text: {message_text[:100]}{'...' if len(message_text) > 100 else ''}"
                        )
                    except Exception as e:
                        # Если не удалось удалить (например, нет прав), просто пропускаем
                        logger.error(
                            f"❌ ОШИБКА УДАЛЕНИЯ (запрещенные символы) | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id}) | Error: {e}"
                        )
                    # Не вызываем handler, чтобы сообщение не обрабатывалось дальше
                    return
                
                # Проверяем наличие ссылок
                if self._has_urls(event):
                    try:
                        await event.delete()
                        # Собираем статистику об удалении
                        if self.statistics:
                            self.statistics.add_checked(chat_id)
                            self.statistics.add_deleted(chat_id, deletion_type="urls")
                        
                        # Логируем удаление
                        logger.info(
                            f"🔗 УДАЛЕНО (ссылка) | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id}) | "
                            f"Text: {message_text[:100]}{'...' if len(message_text) > 100 else ''}"
                        )
                    except Exception as e:
                        # Если не удалось удалить (например, нет прав), просто пропускаем
                        logger.error(
                            f"❌ ОШИБКА УДАЛЕНИЯ (ссылка) | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id}) | Error: {e}"
                        )
                    # Не вызываем handler, чтобы сообщение не обрабатывалось дальше
                    return
                
                # Собираем статистику
                if self.statistics:
                    self.statistics.add_checked(chat_id)
                
                # Получаем вероятность наличия мата
                # predict_proba возвращает список вероятностей
                proba = self.swear_checker.predict_proba(message_text)
                
                # Для одной строки возвращается список с одним float элементом
                # Берем максимальную вероятность из списка
                if isinstance(proba, list):
                    max_proba = max(proba)
                else:
                    max_proba = float(proba)
                
                # Если вероятность мата превышает порог - удаляем сообщение и баним пользователя
                if max_proba >= PROFANITY_THRESHOLD:
                    message_text = event.text or event.caption or ""
                    bot: Bot = data.get("bot")
                    
                    # Удаляем сообщение
                    try:
                        await event.delete()
                        # Собираем статистику об удалении
                        if self.statistics:
                            self.statistics.add_deleted(chat_id, deletion_type="profanity")
                        
                        logger.info(
                            f"🗑️ УДАЛЕНО (мат) | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id}) | "
                            f"Probability: {max_proba:.3f} (threshold: {PROFANITY_THRESHOLD}) | "
                            f"Text: {message_text[:100]}{'...' if len(message_text) > 100 else ''}"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ ОШИБКА УДАЛЕНИЯ (мат) | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id}) | "
                            f"Probability: {max_proba:.3f} | Error: {e} | "
                            f"Text: {message_text[:100]}{'...' if len(message_text) > 100 else ''}"
                        )
                    
                    # Баним пользователя
                    if bot and sender_id:
                        try:
                            await bot.ban_chat_member(chat_id=chat_id, user_id=sender_id)
                            # Собираем статистику о бане
                            if self.statistics:
                                self.statistics.add_banned(chat_id)
                            logger.info(
                                f"🔨 ЗАБАНЕН | Chat: {chat_title} ({chat_id}) | "
                                f"User: {sender_name} (ID: {sender_id}) | "
                                f"Причина: мат (probability: {max_proba:.3f})"
                            )
                            
                            # Отправляем уведомление админам
                            user_username = event.from_user.username if event.from_user and event.from_user.username else None
                            user_first_name = event.from_user.first_name if event.from_user and event.from_user.first_name else "Unknown"
                            
                            await self._send_ban_notification(
                                bot=bot,
                                chat_id=chat_id,
                                chat_title=chat_title,
                                user_id=sender_id,
                                username=user_username,
                                first_name=user_first_name,
                                message_text=message_text,
                                probability=max_proba
                            )
                        except Exception as e:
                            # Если не удалось забанить (например, нет прав или пользователь уже админ)
                            logger.error(
                                f"❌ ОШИБКА БАНА | Chat: {chat_title} ({chat_id}) | "
                                f"User: {sender_name} (ID: {sender_id}) | Error: {e}"
                            )
                    
                    # Не вызываем handler, чтобы сообщение не обрабатывалось дальше
                    return
                else:
                    # Логируем, что сообщение оставлено
                    message_text = event.text or event.caption or ""
                    logger.info(
                        f"✅ ОСТАВЛЕНО | Chat: {chat_title} ({chat_id}) | "
                        f"User: {sender_name} (ID: {sender_id}) | "
                        f"Probability: {max_proba:.3f} (threshold: {PROFANITY_THRESHOLD}) | "
                        f"Text: {message_text[:100]}{'...' if len(message_text) > 100 else ''}"
                    )
        
        # Если проверка пройдена или это не текстовое сообщение - продолжаем обработку
        return await handler(event, data)


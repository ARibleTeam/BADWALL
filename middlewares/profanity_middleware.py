import logging
import re
import asyncio
import tempfile
import os
from typing import Any, Awaitable, Callable, Dict, Optional
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, TelegramObject, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType, ChatMemberStatus, MessageEntityType
from check_swear import SwearingCheck
from config import PROFANITY_THRESHOLD, ALLOWED_CHAT_IDS, ADMIN_IDS
from utils.statistics import Statistics

logger = logging.getLogger(__name__)

try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False
    logger.warning("speech_recognition не установлен. Расшифровка голосовых сообщений недоступна.")

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub не установлен. Конвертация аудио может быть недоступна.")


class ProfanityMiddleware(BaseMiddleware):
    """
    Middleware для автоматической модерации сообщений в Telegram чатах.
    
    Функциональность:
    - Проверка текстовых сообщений на мат с использованием ML-модели
    - Проверка голосовых сообщений (расшифровка и проверка на мат)
    - Проверка на наличие ссылок (URL, t.me, telegram.me)
    - Проверка на запрещенные символы (спецсимволы и нерусские буквы)
    - Автоматическое удаление нарушающих сообщений
    - Бан пользователей за мат (с уведомлениями админам)
    - Сбор статистики по всем типам модерации
    - Исключение администраторов и создателей чата из проверок
    
    Порядок проверок:
    1. Проверка прав администратора (админы пропускаются)
    2. Проверка запрещенных символов (удаление сообщения)
    3. Проверка ссылок (удаление сообщения)
    4. Проверка на мат (удаление + бан пользователя)
    
    Для голосовых сообщений:
    - Расшифровка через Google Speech Recognition (русский язык)
    - Применение тех же проверок, что и для текста
    """
    
    def __init__(self, statistics: Optional[Statistics] = None):
        """
        Инициализация middleware.
        
        Args:
            statistics: Объект для сбора статистики работы бота (опционально)
        """
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
        """
        Проверяет наличие ссылок в сообщении.
        
        Проверяет:
        - Entities сообщения (URL, TEXT_LINK)
        - Caption entities (для сообщений с медиа)
        - Текст сообщения регулярным выражением (http://, https://, www., t.me/, telegram.me/)
        
        Args:
            message: Объект сообщения Telegram
            
        Returns:
            True если найдены ссылки, False иначе
        """
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
    
    def _is_emoji(self, char: str) -> bool:
        """
        Проверяет, является ли символ эмодзи.
        
        Args:
            char: Символ для проверки
            
        Returns:
            True если символ является эмодзи, False иначе
        """
        # Основные диапазоны эмодзи в Unicode
        code_point = ord(char)
        
        # Основные эмодзи (Emoticons, Symbols & Pictographs)
        if 0x1F300 <= code_point <= 0x1F9FF:
            return True
        
        # Дополнительные символы (Miscellaneous Symbols)
        if 0x2600 <= code_point <= 0x26FF:
            return True
        
        # Дингбаты (Dingbats)
        if 0x2700 <= code_point <= 0x27BF:
            return True
        
        # Вариации эмодзи (Variation Selectors)
        if 0xFE00 <= code_point <= 0xFE0F:
            return True
        
        # Модификаторы тона кожи (Skin Tone Modifiers)
        if 0x1F3FB <= code_point <= 0x1F3FF:
            return True
        
        # Региональные индикаторы (для флагов)
        if 0x1F1E6 <= code_point <= 0x1F1FF:
            return True
        
        # Дополнительные символы и пиктограммы
        if 0x1F900 <= code_point <= 0x1F9FF:
            return True
        
        # Символы транспорта и карт
        if 0x1F680 <= code_point <= 0x1F6FF:
            return True
        
        # Дополнительные эмодзи
        if 0x1FA00 <= code_point <= 0x1FAFF:
            return True
        
        return False
    
    def _has_forbidden_chars(self, text: str) -> bool:
        """
        Проверяет наличие запрещенных символов в тексте.
        
        Запрещенные символы:
        - Латиница (a-zA-Z)
        - Спецсимволы: @ # $ % ^ & * + = | \ / < > ~ `
        - Другие нерусские буквы (кириллица других языков, иероглифы и т.д.)
        
        Разрешенные символы:
        - Русские буквы (а-я, А-Я, ё, Ё)
        - Цифры (0-9)
        - Знаки препинания: . , ! ? : ; - ( ) [ ] { } " ' « » — … 
        - Пробелы
        - Эмодзи (все Unicode эмодзи)
        
        Args:
            text: Текст для проверки
            
        Returns:
            True если найдены запрещенные символы, False иначе
        """
        if not text:
            return False
        
        # Проверяем наличие латиницы (a-zA-Z) - это точно нерусские буквы
        if re.search(r'[a-zA-Z]', text):
            return True
        
        # Проверяем наличие запрещенных спецсимволов
        if self.forbidden_special_chars_pattern.search(text):
            return True
        
        # Проверяем наличие других нерусских букв (кириллица других языков, иероглифы и т.д.)
        # Разрешаем только русские буквы (а-я, А-Я, ё, Ё), цифры, пробелы, знаки препинания и эмодзи
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
            # Пропускаем эмодзи
            if self._is_emoji(char):
                continue
            # Если дошли сюда - это запрещенный символ
            return True
        
        return False
    
    async def _transcribe_voice(self, bot: Bot, voice_file_id: str) -> Optional[str]:
        """
        Расшифровывает голосовое сообщение в текст.
        
        Процесс:
        1. Скачивание голосового файла (OGG формат)
        2. Конвертация OGG в WAV (если доступен pydub)
        3. Распознавание речи через Google Speech Recognition (русский язык)
        4. Возврат расшифрованного текста
        
        Args:
            bot: Объект бота для работы с Telegram API
            voice_file_id: ID голосового файла в Telegram
            
        Returns:
            Расшифрованный текст или None в случае ошибки
        """
        if not SPEECH_RECOGNITION_AVAILABLE or not self.recognizer:
            logger.warning("Распознавание речи недоступно")
            return None
        
        ogg_path = None
        wav_path = None
        
        try:
            # Скачиваем файл голосового сообщения
            file = await bot.get_file(voice_file_id)
            
            # Создаем временный файл для сохранения OGG аудио
            with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
                ogg_path = temp_file.name
                
                # Скачиваем файл
                await bot.download_file(file.file_path, ogg_path)
            
            # Конвертируем OGG в WAV, если доступен pydub
            if PYDUB_AVAILABLE:
                try:
                    # Конвертируем OGG в WAV
                    loop = asyncio.get_event_loop()
                    wav_path = await loop.run_in_executor(
                        None,
                        self._convert_ogg_to_wav,
                        ogg_path
                    )
                except Exception as e:
                    logger.warning(f"Не удалось конвертировать OGG в WAV: {e}. Пробуем использовать OGG напрямую.")
                    wav_path = ogg_path
            else:
                # Пробуем использовать OGG напрямую (может не работать)
                wav_path = ogg_path
            
            # Распознаем речь (запускаем в executor, т.к. speech_recognition синхронный)
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None,
                self._recognize_audio,
                wav_path
            )
            
            return text
                
        except Exception as e:
            logger.error(f"Ошибка при расшифровке голосового сообщения: {e}")
            return None
        finally:
            # Удаляем временные файлы
            files_to_delete = []
            if ogg_path:
                files_to_delete.append(ogg_path)
            if wav_path and wav_path != ogg_path:
                files_to_delete.append(wav_path)
            
            for file_path in files_to_delete:
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    logger.debug(f"Не удалось удалить временный файл {file_path}: {e}")
    
    def _convert_ogg_to_wav(self, ogg_path: str) -> str:
        """
        Конвертирует OGG файл в WAV формат для распознавания речи.
        
        Требует установленный pydub и ffmpeg.
        
        Args:
            ogg_path: Путь к OGG файлу
            
        Returns:
            Путь к созданному WAV файлу
        """
        wav_path = ogg_path.replace('.ogg', '.wav')
        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")
        return wav_path
    
    def _recognize_audio(self, audio_path: str) -> Optional[str]:
        """
        Синхронная функция для распознавания речи в аудио файле.
        
        Использует Google Speech Recognition API с русским языком (ru-RU).
        Требует интернет-соединение.
        
        Args:
            audio_path: Путь к аудио файлу (WAV или OGG)
            
        Returns:
            Распознанный текст или None в случае ошибки
        """
        try:
            with sr.AudioFile(audio_path) as source:
                # Подстраиваемся под уровень шума
                self.recognizer.adjust_for_ambient_noise(source)
                # Записываем аудио
                audio = self.recognizer.record(source)
            
            # Распознаем речь (используем Google Speech Recognition)
            # Указываем язык - русский
            text = self.recognizer.recognize_google(audio, language='ru-RU')
            return text
        except sr.UnknownValueError:
            logger.warning("Не удалось распознать речь в голосовом сообщении")
            return None
        except sr.RequestError as e:
            logger.error(f"Ошибка сервиса распознавания речи: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при распознавании аудио: {e}")
            return None
    
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
        """
        Отправляет уведомление всем админам о бане пользователя.
        
        Уведомление содержит:
        - Информацию о пользователе (имя, username, ID)
        - Информацию о чате (название, Chat ID)
        - Причину бана (вероятность мата)
        - Текст сообщения, из-за которого забанили
        
        В уведомлении есть инлайн-кнопки:
        - "✅ Разбанить" - разбанивает пользователя в указанном чате
        - "🗑️ Скрыть" - удаляет уведомление
        
        Args:
            bot: Объект бота для отправки сообщений
            chat_id: ID чата, где произошел бан
            chat_title: Название чата
            user_id: ID забаненного пользователя
            username: Username пользователя (опционально)
            first_name: Имя пользователя
            message_text: Текст сообщения, из-за которого забанили
            probability: Вероятность наличия мата (0.0-1.0)
        """
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
        """
        Основной метод middleware для обработки всех сообщений.
        
        Обрабатывает:
        - Текстовые сообщения
        - Сообщения с подписями (медиа)
        - Голосовые сообщения (расшифровка и проверка)
        
        Порядок проверок:
        1. Пропуск личных сообщений (модерация только для групп)
        2. Проверка разрешенных чатов (ALLOWED_CHAT_IDS)
        3. Проверка прав администратора (админы пропускаются)
        4. Для голосовых: расшифровка и проверка
        5. Для текста: проверка запрещенных символов → ссылок → мата
        
        Действия при нарушениях:
        - Запрещенные символы: удаление сообщения
        - Ссылки: удаление сообщения
        - Мат: удаление сообщения + бан пользователя + уведомление админам
        
        Args:
            handler: Следующий обработчик в цепочке
            event: Событие Telegram (Message)
            data: Данные контекста (содержит bot и другие данные)
            
        Returns:
            Результат обработки или None (если сообщение удалено)
        """
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
            
            # Получаем информацию об отправителе (для всех типов сообщений)
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
            
            # Обрабатываем голосовые сообщения
            if event.voice:
                bot: Bot = data.get("bot")
                if bot and event.voice:
                    transcribed_text = await self._transcribe_voice(bot, event.voice.file_id)
                    
                    if transcribed_text:
                        logger.info(
                            f"🎤 Расшифровано голосовое сообщение | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id}) | Text: {transcribed_text[:100]}"
                        )
                        
                        # Применяем те же проверки, что и для текстовых сообщений
                        # Проверяем запрещенные символы
                        if self._has_forbidden_chars(transcribed_text):
                            try:
                                await event.delete()
                                if self.statistics:
                                    self.statistics.add_checked(chat_id)
                                    self.statistics.add_deleted(chat_id, deletion_type="forbidden_chars")
                                logger.info(
                                    f"🚫 УДАЛЕНО (голос, запрещенные символы) | Chat: {chat_title} ({chat_id}) | "
                                    f"User: {sender_name} (ID: {sender_id})"
                                )
                            except Exception as e:
                                logger.error(f"❌ ОШИБКА УДАЛЕНИЯ (голос, запрещенные символы): {e}")
                            return
                        
                        # Проверяем на мат
                        proba = self.swear_checker.predict_proba(transcribed_text)
                        max_proba = max(proba) if isinstance(proba, list) else float(proba)
                        
                        if max_proba >= PROFANITY_THRESHOLD:
                            # Удаляем сообщение и баним
                            try:
                                await event.delete()
                                if self.statistics:
                                    self.statistics.add_checked(chat_id)
                                    self.statistics.add_deleted(chat_id, deletion_type="profanity")
                                
                                logger.info(
                                    f"🗑️ УДАЛЕНО (голос, мат) | Chat: {chat_title} ({chat_id}) | "
                                    f"User: {sender_name} (ID: {sender_id}) | "
                                    f"Probability: {max_proba:.3f} | Text: {transcribed_text[:100]}"
                                )
                                
                                # Баним пользователя
                                if bot and sender_id:
                                    try:
                                        await bot.ban_chat_member(chat_id=chat_id, user_id=sender_id)
                                        if self.statistics:
                                            self.statistics.add_banned(chat_id)
                                        
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
                                            message_text=f"[Голосовое сообщение] {transcribed_text}",
                                            probability=max_proba
                                        )
                                        
                                        logger.info(
                                            f"🔨 ЗАБАНЕН (голос) | Chat: {chat_title} ({chat_id}) | "
                                            f"User: {sender_name} (ID: {sender_id})"
                                        )
                                    except Exception as e:
                                        logger.error(f"❌ ОШИБКА БАНА (голос): {e}")
                            except Exception as e:
                                logger.error(f"❌ ОШИБКА УДАЛЕНИЯ (голос, мат): {e}")
                            return
                    else:
                        # Если не удалось расшифровать, пропускаем (не удаляем голосовое сообщение)
                        logger.warning(
                            f"⚠️ Не удалось расшифровать голосовое сообщение | Chat: {chat_title} ({chat_id}) | "
                            f"User: {sender_name} (ID: {sender_id})"
                        )
            
            # Проверяем текстовые сообщения и сообщения с подписями
            if event.text or event.caption:
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


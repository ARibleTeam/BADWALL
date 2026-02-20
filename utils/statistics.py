from datetime import datetime
from typing import Dict
from collections import defaultdict


class Statistics:
    """Класс для сбора статистики работы бота"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Сброс статистики (вызывается ежедневно)"""
        self.total_checked = 0  # Всего проверено сообщений
        self.total_deleted = 0   # Всего удалено сообщений
        self.deleted_forbidden_chars = 0  # Удалено за запрещенные символы
        self.deleted_urls = 0  # Удалено за ссылки
        self.deleted_profanity = 0  # Удалено за мат
        self.total_banned = 0  # Всего забанено пользователей
        self.by_chat: Dict[int, Dict[str, int]] = defaultdict(lambda: {
            "checked": 0,
            "deleted": 0,
            "deleted_forbidden_chars": 0,
            "deleted_urls": 0,
            "deleted_profanity": 0,
            "banned": 0
        })
        self.start_date = datetime.now()
    
    def add_checked(self, chat_id: int):
        """Добавить проверенное сообщение"""
        self.total_checked += 1
        self.by_chat[chat_id]["checked"] += 1
    
    def add_deleted(self, chat_id: int, deletion_type: str = "unknown"):
        """Добавить удаленное сообщение
        
        Args:
            chat_id: ID чата
            deletion_type: Тип удаления - "forbidden_chars", "urls", "profanity"
        """
        self.total_deleted += 1
        self.by_chat[chat_id]["deleted"] += 1
        
        if deletion_type == "forbidden_chars":
            self.deleted_forbidden_chars += 1
            self.by_chat[chat_id]["deleted_forbidden_chars"] += 1
        elif deletion_type == "urls":
            self.deleted_urls += 1
            self.by_chat[chat_id]["deleted_urls"] += 1
        elif deletion_type == "profanity":
            self.deleted_profanity += 1
            self.by_chat[chat_id]["deleted_profanity"] += 1
    
    def add_banned(self, chat_id: int):
        """Добавить забаненного пользователя"""
        self.total_banned += 1
        self.by_chat[chat_id]["banned"] += 1
    
    def get_stats_text(self) -> str:
        """Получить текст статистики для отправки"""
        if self.total_checked == 0:
            return "📊 Статистика за сегодня:\n\nНет активности."
        
        deletion_rate = (self.total_deleted / self.total_checked * 100) if self.total_checked > 0 else 0
        
        text = f"📊 <b>Статистика работы бота</b>\n\n"
        text += f"📅 Период: {self.start_date.strftime('%d.%m.%Y')} - {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        text += f"📝 Всего проверено сообщений: <b>{self.total_checked}</b>\n"
        text += f"🗑️ Всего удалено сообщений: <b>{self.total_deleted}</b>\n"
        text += f"📈 Процент удалений: <b>{deletion_rate:.1f}%</b>\n\n"
        
        # Детализация по типам удалений
        text += "<b>Детализация удалений:</b>\n"
        text += f"🚫 Запрещенные символы: <b>{self.deleted_forbidden_chars}</b>\n"
        text += f"🔗 За ссылки: <b>{self.deleted_urls}</b>\n"
        text += f"🗑️ За мат: <b>{self.deleted_profanity}</b>\n"
        text += f"🔨 Забанено пользователей: <b>{self.total_banned}</b>\n\n"
        
        if len(self.by_chat) > 1:
            text += "<b>По чатам:</b>\n"
            for chat_id, stats in self.by_chat.items():
                chat_deletion_rate = (stats["deleted"] / stats["checked"] * 100) if stats["checked"] > 0 else 0
                text += f"\n• <b>Чат {chat_id}:</b>\n"
                text += f"  Проверено: {stats['checked']}\n"
                text += f"  Удалено: {stats['deleted']} ({chat_deletion_rate:.1f}%)\n"
                if stats["deleted_forbidden_chars"] > 0:
                    text += f"  └ Запрещенные символы: {stats['deleted_forbidden_chars']}\n"
                if stats["deleted_urls"] > 0:
                    text += f"  └ За ссылки: {stats['deleted_urls']}\n"
                if stats["deleted_profanity"] > 0:
                    text += f"  └ За мат: {stats['deleted_profanity']}\n"
                if stats["banned"] > 0:
                    text += f"  └ Забанено: {stats['banned']}\n"
        
        return text


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
        self.by_chat: Dict[int, Dict[str, int]] = defaultdict(lambda: {
            "checked": 0,
            "deleted": 0
        })
        self.start_date = datetime.now()
    
    def add_checked(self, chat_id: int):
        """Добавить проверенное сообщение"""
        self.total_checked += 1
        self.by_chat[chat_id]["checked"] += 1
    
    def add_deleted(self, chat_id: int):
        """Добавить удаленное сообщение"""
        self.total_deleted += 1
        self.by_chat[chat_id]["deleted"] += 1
    
    def get_stats_text(self) -> str:
        """Получить текст статистики для отправки"""
        if self.total_checked == 0:
            return "📊 Статистика за сегодня:\n\nНет активности."
        
        deletion_rate = (self.total_deleted / self.total_checked * 100) if self.total_checked > 0 else 0
        
        text = f"📊 <b>Статистика работы бота</b>\n\n"
        text += f"📅 Период: {self.start_date.strftime('%d.%m.%Y')} - {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        text += f"📝 Всего проверено сообщений: <b>{self.total_checked}</b>\n"
        text += f"🗑️ Удалено сообщений: <b>{self.total_deleted}</b>\n"
        text += f"📈 Процент удалений: <b>{deletion_rate:.1f}%</b>\n\n"
        
        if len(self.by_chat) > 1:
            text += "<b>По чатам:</b>\n"
            for chat_id, stats in self.by_chat.items():
                chat_deletion_rate = (stats["deleted"] / stats["checked"] * 100) if stats["checked"] > 0 else 0
                text += f"• Чат {chat_id}: проверено {stats['checked']}, удалено {stats['deleted']} ({chat_deletion_rate:.1f}%)\n"
        
        return text


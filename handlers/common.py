from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatType
import logging

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    # Отвечаем только в личных сообщениях
    if message.chat.type != ChatType.PRIVATE:
        return
    
    await message.answer(
        "Привет! Я бот для модерации чата.\n"
        "Я автоматически проверяю все сообщения на наличие нецензурной лексики "
        "и удаляю сообщения с высокой вероятностью мата."
    )

    await message.answer(
        "Этот бот автоматически модерирует чат:\n\n"
        "• Проверяет все сообщения на наличие мата\n"
        "• Удаляет сообщения с вероятностью мата\n"
        "• Работает автоматически, не требует команд\n\n"
        "Для работы бот должен быть администратором группы "
        "с правами на удаление сообщений."
    )


@router.message()
async def echo_handler(message: Message):
    """Обработчик всех остальных сообщений"""
    # Сообщения уже проверены middleware, если дошли сюда - они прошли проверку
    pass


@router.callback_query(lambda c: c.data and c.data.startswith("unban_"))
async def handle_unban_callback(callback: CallbackQuery, bot: Bot):
    """Обработчик кнопки разбана"""
    try:
        # Формат callback_data: "unban_{chat_id}_{user_id}"
        parts = callback.data.split("_")
        if len(parts) != 3:
            await callback.answer("Ошибка: неверный формат данных", show_alert=True)
            return
        
        chat_id = int(parts[1])
        user_id = int(parts[2])
        
        # Разбаниваем пользователя
        try:
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
            await callback.answer("✅ Пользователь разбанен", show_alert=False)
            
            # Обновляем текст сообщения
            original_text = callback.message.text or callback.message.caption or ""
            new_text = original_text + "\n\n✅ <b>Пользователь разбанен</b>"
            
            try:
                await callback.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")
            except:
                # Если не удалось отредактировать (например, уже отредактировано), просто ответим
                pass
            
            logger.info(f"Пользователь {user_id} разбанен в чате {chat_id} админом {callback.from_user.id}")
            
        except Exception as e:
            await callback.answer(f"❌ Ошибка при разбане: {e}", show_alert=True)
            logger.error(f"Ошибка при разбане пользователя {user_id} в чате {chat_id}: {e}")
            
    except Exception as e:
        await callback.answer("❌ Произошла ошибка", show_alert=True)
        logger.error(f"Ошибка в обработчике разбана: {e}")


@router.callback_query(lambda c: c.data and c.data == "hide_ban_notification")
async def handle_hide_ban_notification(callback: CallbackQuery):
    """Обработчик кнопки скрытия уведомления о бане"""
    try:
        await callback.message.delete()
        await callback.answer("Уведомление скрыто", show_alert=False)
    except Exception as e:
        await callback.answer("❌ Не удалось скрыть уведомление", show_alert=True)
        logger.error(f"Ошибка при скрытии уведомления: {e}")


from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType

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


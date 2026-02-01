from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from config import ALLOWED_CHAT_IDS

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    # Проверка разрешенного чата (на всякий случай, хотя middleware уже проверил)
    if message.chat.id not in ALLOWED_CHAT_IDS:
        return
    
    await message.answer(
        "Привет! Я бот для модерации чата.\n"
        "Я автоматически проверяю все сообщения на наличие нецензурной лексики "
        "и удаляю сообщения с высокой вероятностью мата."
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    # Проверка разрешенного чата (на всякий случай, хотя middleware уже проверил)
    if message.chat.id not in ALLOWED_CHAT_IDS:
        return
    
    await message.answer(
        "Этот бот автоматически модерирует чат:\n\n"
        "• Проверяет все сообщения на наличие мата\n"
        "• Удаляет сообщения с вероятностью мата ≥ 0.7\n"
        "• Работает автоматически, не требует команд\n\n"
        "Для работы бот должен быть администратором группы "
        "с правами на удаление сообщений."
    )


@router.message(Command("chat_id"))
async def cmd_chat_id(message: Message):
    """Обработчик команды /chat_id - показывает ID текущего чата"""
    # Проверка разрешенного чата (на всякий случай, хотя middleware уже проверил)
    if message.chat.id not in ALLOWED_CHAT_IDS:
        return
    
    chat_id = message.chat.id
    chat_type = message.chat.type
    chat_title = message.chat.title or "Личные сообщения"
    
    await message.answer(
        f"📊 Информация о чате:\n\n"
        f"• Название: {chat_title}\n"
        f"• Тип: {chat_type}\n"
        f"• Chat ID: <code>{chat_id}</code>\n\n"
        f"Этот ID можно добавить в ALLOWED_CHAT_IDS в файле .env",
        parse_mode="HTML"
    )


@router.message()
async def echo_handler(message: Message):
    """Обработчик всех остальных сообщений"""
    # Сообщения уже проверены middleware, если дошли сюда - они прошли проверку
    pass


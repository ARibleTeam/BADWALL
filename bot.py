import asyncio
import logging
from pytz import timezone
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import BOT_TOKEN, ADMIN_IDS, STATS_TIME
from middlewares.profanity_middleware import ProfanityMiddleware
from handlers import common
from utils.statistics import Statistics

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальный объект статистики
statistics = Statistics()


async def send_daily_stats(bot: Bot):
    """Отправка ежедневной статистики админам"""
    try:
        stats_text = statistics.get_stats_text()
        
        # Отправляем статистику всем админам
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, stats_text, parse_mode="HTML")
                logger.info(f"Статистика отправлена админу {admin_id}")
            except Exception as e:
                logger.error(f"Не удалось отправить статистику админу {admin_id}: {e}")
        
        # Сбрасываем статистику после отправки
        statistics.reset()
        logger.info("Статистика сброшена, начинаем новый день")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке статистики: {e}")


async def main():
    """Основная функция запуска бота"""
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    
    # Регистрация middleware с передачей объекта статистики
    dp.message.middleware(ProfanityMiddleware(statistics=statistics))
    
    # Регистрация роутеров
    dp.include_router(common.router)
    
    # Настройка планировщика для ежедневной отправки статистики
    # Используем московское время
    moscow_tz = timezone('Europe/Moscow')
    scheduler = AsyncIOScheduler(timezone=moscow_tz)
    
    # Парсим время из конфига (формат "HH:MM")
    hour, minute = map(int, STATS_TIME.split(":"))
    
    # Настраиваем задачу на ежедневную отправку в указанное время (по московскому времени)
    scheduler.add_job(
        send_daily_stats,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=moscow_tz),
        args=[bot],
        id="daily_stats",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info(f"Планировщик запущен. Статистика будет отправляться ежедневно в {STATS_TIME}")
    
    # Запуск polling
    logger.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")


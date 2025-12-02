from datetime import datetime, timedelta
from typing import List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import SERVICES, WORKING_HOURS, BOOKING_DAYS_AHEAD, TIME_BUTTONS_PER_ROW
from database import BookingDAO, Booking


async def get_date_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора даты (исключая выходные дни)"""
    from database import BarberDayOffDAO  # Импорт внутри функции, чтобы избежать циклического импорта
    
    keyboard = []
    today = datetime.now()
    
    # Получаем все выходные дни
    days_off = await BarberDayOffDAO.get_all()
    days_off_dates = [day_off.date for day_off in days_off]
    
    for i in range(BOOKING_DAYS_AHEAD):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m.%Y")
        
        # Пропускаем выходные дни
        if date_str in days_off_dates:
            continue
        
        day_name = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][date.weekday()]
        
        if i == 0:
            button_text = f"🔥 Сегодня ({date_str})"
        elif i == 1:
            button_text = f"⚡ Завтра ({date_str})"
        else:
            button_text = f"{day_name} {date_str}"
        
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"date_{date_str}")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def get_time_keyboard(date: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора времени с учетом занятых слотов"""
    keyboard = []
    row = []
    
    for i, time in enumerate(WORKING_HOURS):
        # Проверяем, занято ли время
        existing_booking = await BookingDAO.get_by_date_time(date, time)
        
        if existing_booking:
            # Занятое время - красная кнопка
            button_text = f"🔴 {time}"
            callback_data = f"busy_{time}"
        else:
            # Свободное время
            button_text = time
            callback_data = f"time_{time}"
        
        row.append(InlineKeyboardButton(text=button_text, callback_data=callback_data))
        
        if (i + 1) % TIME_BUTTONS_PER_ROW == 0:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_service_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора услуги"""
    keyboard = []
    
    for service_id, service_info in SERVICES.items():
        button_text = (
            f"{service_info['emoji']} {service_info['name']}\n"
            f"💰 {service_info['price']}₽ | ⏱ {service_info['duration']} мин"
        )
        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"service_{service_id}"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_my_bookings_keyboard(bookings: List[Booking]) -> InlineKeyboardMarkup:
    """Клавиатура со списком записей пользователя"""
    keyboard = []
    
    for booking in bookings:
        button_text = f"❌ Отменить запись #{booking.id}"
        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"cancel_booking_{booking.id}"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cancel_confirm_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения отмены записи"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="✅ Да, отменить",
                callback_data=f"confirm_cancel_{booking_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="back_to_bookings"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура администратора (барбера)"""
    keyboard = [
        [
            InlineKeyboardButton(text="📅 Добавить выходной", callback_data="admin_add_dayoff"),
            InlineKeyboardButton(text="🗑 Удалить выходной", callback_data="admin_remove_dayoff")
        ],
        [
            InlineKeyboardButton(text="📋 Посмотреть выходные", callback_data="admin_view_dayoffs"),
            InlineKeyboardButton(text="👥 Активные записи", callback_data="admin_view_bookings")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def get_dayoff_dates_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с выходными днями для удаления"""
    from database import BarberDayOffDAO  # Импорт внутри функции
    
    keyboard = []
    days_off = await BarberDayOffDAO.get_upcoming(20)
    
    for day_off in days_off:
        button_text = f"❌ {day_off.date}"
        if day_off.reason:
            button_text += f" ({day_off.reason[:20]}...)"
        
        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"remove_dayoff_{day_off.date}"
            )
        ])
    
    # Кнопка "Назад"
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
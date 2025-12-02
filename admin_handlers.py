# admin_handlers.py
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import BARBER_CHAT_ID
from database import BookingDAO, BarberDayOffDAO
from keyboards import get_admin_keyboard, get_dayoff_dates_keyboard

router = Router()


# Проверка, является ли пользователь барбером
def is_barber(user_id: int) -> bool:
    return str(user_id) == BARBER_CHAT_ID


# Состояния FSM для управления выходными
class AdminStates(StatesGroup):
    waiting_for_dayoff_date = State()
    waiting_for_dayoff_reason = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Панель администратора"""
    if not is_barber(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    
    keyboard = get_admin_keyboard()
    
    await message.answer(
        "👨‍✈️ <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню админки"""
    await state.clear()
    keyboard = get_admin_keyboard()
    
    await callback.message.edit_text(
        "👨‍✈️ <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_dayoff")
async def admin_add_dayoff(callback: CallbackQuery, state: FSMContext):
    """Добавить выходной день"""
    if not is_barber(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    # Создаем клавиатуру с датами на 30 дней вперед
    keyboard = []
    today = datetime.now()
    
    for i in range(1, 31):  # Начинаем с завтрашнего дня
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m.%Y")
        day_name = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][date.weekday()]
        
        button_text = f"{day_name} {date_str}"
        
        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"select_dayoff_date_{date_str}"
            )
        ])
    
    # Кнопка "Назад"
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")
    ])
    
    await callback.message.edit_text(
        "📅 <b>Выберите дату для выходного:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode='HTML'
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_dayoff_date_"))
async def select_dayoff_date(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора даты для выходного"""
    date = callback.data.replace("select_dayoff_date_", "")
    
    # Проверяем, не является ли уже выходным
    existing = await BarberDayOffDAO.get_by_date(date)
    if existing:
        await callback.answer(f"❌ {date} уже отмечен как выходной", show_alert=True)
        return
    
    await state.update_data(dayoff_date=date)
    await state.set_state(AdminStates.waiting_for_dayoff_reason)
    
    await callback.message.edit_text(
        f"📅 <b>Дата:</b> {date}\n\n"
        f"✏️ <b>Введите причину выходного (необязательно):</b>\n\n"
        f"<i>Или отправьте '-' чтобы пропустить</i>",
        parse_mode='HTML'
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_dayoff_reason)
async def process_dayoff_reason(message: Message, state: FSMContext, bot: Bot):
    """Обработка причины выходного"""
    reason = message.text.strip()
    if reason == "-":
        reason = None
    
    data = await state.get_data()
    date = data.get('dayoff_date')
    
    # Добавляем выходной день
    day_off = await BarberDayOffDAO.create(date, reason)
    
    # Отменяем все активные записи на эту дату
    bookings = await BookingDAO.get_by_date(date)
    cancelled_count = 0
    
    for booking in bookings:
        success = await BookingDAO.cancel(booking.id)
        if success:
            cancelled_count += 1
            
            # Уведомляем клиента об отмене
            try:
                client_message = f"""
❌ <b>Запись отменена!</b>

Ваша запись на {booking.booking_date} в {booking.booking_time} была отменена, так как это день выходного барбера.

🆔 <b>Номер записи:</b> <code>{booking.id}</code>
💈 <b>Услуга:</b> {booking.service_name}
📅 <b>Дата:</b> {booking.booking_date}
🕐 <b>Время:</b> {booking.booking_time}

Для новой записи используйте /book

Приносим извинения за неудобства! 😔
                """
                
                await bot.send_message(
                    chat_id=booking.user_telegram_id,
                    text=client_message,
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Ошибка отправки уведомления клиенту: {e}")
    
    # Отправляем подтверждение барберу
    reason_text = f" ({reason})" if reason else ""
    cancelled_text = f"\n\n❌ Отменено записей: {cancelled_count}" if cancelled_count > 0 else ""
    
    await message.answer(
        f"✅ <b>Выходной день добавлен!</b>\n\n"
        f"📅 <b>Дата:</b> {date}{reason_text}{cancelled_text}\n\n"
        f"Теперь на эту дату нельзя записаться.",
        parse_mode='HTML'
    )
    
    # Возвращаемся в меню админки
    await state.clear()
    keyboard = get_admin_keyboard()
    await message.answer(
        "👨‍✈️ <b>Панель администратора</b>\n\nВыберите действие:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )


@router.callback_query(F.data == "admin_remove_dayoff")
async def admin_remove_dayoff(callback: CallbackQuery):
    """Удалить выходной день"""
    if not is_barber(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    keyboard = await get_dayoff_dates_keyboard()
    
    await callback.message.edit_text(
        "🗑 <b>Выберите выходной день для удаления:</b>",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_dayoff_"))
async def remove_dayoff(callback: CallbackQuery):
    """Обработка удаления выходного дня"""
    date = callback.data.replace("remove_dayoff_", "")
    
    success = await BarberDayOffDAO.delete(date)
    
    if success:
        await callback.answer(f"✅ Выходной {date} удален", show_alert=True)
        
        # Возвращаемся к списку выходных
        keyboard = await get_dayoff_dates_keyboard()
        await callback.message.edit_text(
            "🗑 <b>Выберите выходной день для удаления:</b>",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    else:
        await callback.answer(f"❌ Ошибка удаления", show_alert=True)


@router.callback_query(F.data == "admin_view_dayoffs")
async def admin_view_dayoffs(callback: CallbackQuery):
    """Просмотр всех выходных дней"""
    if not is_barber(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    days_off = await BarberDayOffDAO.get_upcoming(30)
    
    if not days_off:
        text = "📅 <b>Выходные дни не установлены</b>"
    else:
        text = "📅 <b>Ближайшие выходные дни:</b>\n\n"
        for day_off in days_off:
            reason_text = f" - {day_off.reason}" if day_off.reason else ""
            text += f"❌ <b>{day_off.date}</b>{reason_text}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer()


@router.callback_query(F.data == "admin_view_bookings")
async def admin_view_bookings(callback: CallbackQuery):
    """Просмотр всех активных записей"""
    if not is_barber(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    bookings = await BookingDAO.get_all_active()
    
    if not bookings:
        text = "📋 <b>Нет активных записей</b>"
    else:
        text = "📋 <b>Все активные записи:</b>\n\n"
        for booking in bookings:
            text += (
                f"🆔 <code>{booking.id}</code>\n"
                f"👤 {booking.user_name}\n"
                f"📞 {booking.user_phone}\n"
                f"📅 {booking.booking_date} в {booking.booking_time}\n"
                f"💈 {booking.service_name}\n"
                f"💰 {booking.service_price}₽\n"
                f"────────────────────\n"
            )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer()
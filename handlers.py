from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from database import BarberDayOffDAO
from config import (
    BARBER_CHAT_ID,
    SERVICES,
    WORKING_HOURS,
    BARBERSHOP_INFO,
    BOOKING_DAYS_AHEAD,
    TIME_BUTTONS_PER_ROW
)
from database import UserDAO, BookingDAO
from keyboards import (
    get_date_keyboard,
    get_time_keyboard,
    get_service_keyboard,
    get_my_bookings_keyboard,
    get_cancel_confirm_keyboard
)

router = Router()


# Состояния FSM
class BookingStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    selecting_date = State()
    selecting_time = State()
    selecting_service = State()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Начало работы с ботом"""
    user = message.from_user
    
    welcome_text = f"""
👋 Привет, {user.first_name}!

Добро пожаловать в барбершоп <b>{BARBERSHOP_INFO['name']}</b>

💈 Я помогу вам записаться на стрижку. 
Процесс займет всего минуту!

📋 <b>Доступные команды:</b>
/book - Записаться на стрижку
/my_bookings - Мои записи
/cancel - Отменить процесс записи
    """
    
    await message.answer(welcome_text, parse_mode='HTML')


@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext):
    """Начало процесса записи"""
    # Сохраняем telegram_id и username
    await state.update_data(
        telegram_id=message.from_user.id,
        username=f"@{message.from_user.username}" if message.from_user.username else "не указан"
    )
    
    # Проверяем, есть ли пользователь в базе
    user = await UserDAO.get_by_telegram_id(message.from_user.id)
    
    if user:
        # Пользователь уже есть, предлагаем использовать сохраненные данные
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, использовать", callback_data="use_saved_data")],
            [InlineKeyboardButton(text="✏️ Ввести новые данные", callback_data="enter_new_data")]
        ])
        
        await message.answer(
            f"<b>У вас уже есть сохраненные данные:</b>\n\n"
            f"👤 <b>Имя:</b> {user.full_name}\n"
            f"📞 <b>Телефон:</b> {user.phone}\n\n"
            f"<b>Использовать эти данные?</b>",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        await state.set_state(BookingStates.selecting_date)
    else:
        # Новый пользователь
        await message.answer(
            "<b>📝 Шаг 1/5: Как вас зовут?</b>\n\nВведите ваше имя:",
            parse_mode='HTML'
        )
        await state.set_state(BookingStates.waiting_for_name)


@router.callback_query(F.data == "use_saved_data")
async def use_saved_data(callback: CallbackQuery, state: FSMContext):
    """Использовать сохраненные данные"""
    user = await UserDAO.get_by_telegram_id(callback.from_user.id)
    
    await state.update_data(
        name=user.full_name,
        phone=user.phone
    )
    
    keyboard = get_date_keyboard()
    
    await callback.message.edit_text(
        f"Отлично! 👍\n\n<b>📅 Шаг 2/5: Выберите дату</b>",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    
    await state.set_state(BookingStates.selecting_date)
    await callback.answer()


@router.callback_query(F.data == "enter_new_data")
async def enter_new_data(callback: CallbackQuery, state: FSMContext):
    """Ввести новые данные"""
    await callback.message.edit_text(
        "<b>📝 Шаг 1/5: Как вас зовут?</b>\n\nВведите ваше имя:",
        parse_mode='HTML'
    )
    await state.set_state(BookingStates.waiting_for_name)
    await callback.answer()


@router.message(BookingStates.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext):
    """Обработка имени"""
    await state.update_data(name=message.text)
    
    await message.answer(
        f"Отлично, {message.text}! 👍\n\n"
        f"<b>📞 Шаг 2/5: Введите номер телефона</b>\n\n"
        f"<i>Формат: +7 (999) 123-45-67 или 89991234567</i>",
        parse_mode='HTML'
    )
    
    await state.set_state(BookingStates.waiting_for_phone)


@router.message(BookingStates.waiting_for_phone, F.text)
async def process_phone(message: Message, state: FSMContext):
    """Обработка телефона"""
    await state.update_data(phone=message.text)
    
    keyboard = await get_date_keyboard()   

    await message.answer(
        "<b>📅 Шаг 3/5: Выберите дату</b>",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    
    await state.set_state(BookingStates.selecting_date)



@router.callback_query(BookingStates.selecting_date, F.data.startswith("date_"))
async def process_date(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора даты"""
    date = callback.data.replace("date_", "")
    
    # Проверяем, не является ли день выходным
    day_off = await BarberDayOffDAO.get_by_date(date)
    if day_off:
        reason_text = f" ({day_off.reason})" if day_off.reason else ""
        await callback.answer(
            f"❌ {date} - выходной день барбера{reason_text}! Выберите другую дату.", 
            show_alert=True
        )
        return
    
    await state.update_data(date=date)
    
    # Получаем занятые слоты на эту дату
    keyboard = await get_time_keyboard(date)
    
    await callback.message.edit_text(
        f"📅 <b>Дата:</b> {date}\n\n"
        f"<b>🕐 Шаг 4/5: Выберите время</b>\n\n"
        f"<i>🔴 - Время занято</i>",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    
    await state.set_state(BookingStates.selecting_time)
    await callback.answer()


@router.callback_query(BookingStates.selecting_time, F.data.startswith("time_"))
async def process_time(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора времени"""
    time = callback.data.replace("time_", "")
    await state.update_data(time=time)
    
    data = await state.get_data()
    
    # Проверяем, что время еще свободно
    existing_booking = await BookingDAO.get_by_date_time(data['date'], time)
    if existing_booking:
        await callback.answer("❌ Это время уже занято! Выберите другое.", show_alert=True)
        return
    
    keyboard = get_service_keyboard()
    
    await callback.message.edit_text(
        f"📅 <b>Дата:</b> {data['date']}\n"
        f"🕐 <b>Время:</b> {time}\n\n"
        f"<b>💈 Шаг 5/5: Выберите услугу</b>",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    
    await state.set_state(BookingStates.selecting_service)
    await callback.answer()


@router.callback_query(BookingStates.selecting_service, F.data.startswith("service_"))
async def confirm_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение и сохранение записи"""
    service_id = callback.data.replace("service_", "")
    service_info = SERVICES[service_id]
    
    data = await state.get_data()
    
    # Еще раз проверяем доступность времени
    existing_booking = await BookingDAO.get_by_date_time(data['date'], data['time'])
    if existing_booking:
        await callback.answer("❌ Это время уже занято! Начните запись заново /book", show_alert=True)
        await state.clear()
        return
    
    # Сохраняем пользователя в БД
    await UserDAO.create_or_update(
        telegram_id=data['telegram_id'],
        username=data.get('username'),
        full_name=data['name'],
        phone=data['phone']
    )
    
    # Создаем запись
    booking = await BookingDAO.create(
        user_telegram_id=data['telegram_id'],
        user_name=data['name'],
        user_phone=data['phone'],
        user_username=data.get('username'),
        booking_date=data['date'],
        booking_time=data['time'],
        service_type=service_id,
        service_name=service_info['name'],
        service_price=service_info['price'],
        service_duration=service_info['duration']
    )
    
    # Формируем сообщение для клиента
    client_message = f"""
✅ <b>Запись подтверждена!</b>

🆔 <b>Номер записи:</b> <code>{booking.id}</code>

👤 <b>Имя:</b> {data['name']}
📞 <b>Телефон:</b> {data['phone']}
🆔 <b>Telegram:</b> {data.get('username', 'не указан')}
📅 <b>Дата:</b> {data['date']}
🕐 <b>Время:</b> {data['time']}
💈 <b>Услуга:</b> {service_info['emoji']} {service_info['name']}
⏱ <b>Длительность:</b> {service_info['duration']} мин
💰 <b>Стоимость:</b> {service_info['price']}₽

📍 <b>Адрес:</b> {BARBERSHOP_INFO['address']}
☎️ <b>Контакт барбера:</b> {BARBERSHOP_INFO['phone']}

⏰ <i>Пожалуйста, приходите за 5 минут до начала.</i>
<i>Если планы изменятся, используйте /my_bookings для отмены.</i>

<b>До встречи! 💈✨</b>
    """
    
    await callback.message.edit_text(client_message, parse_mode='HTML')
    
    # Отправляем уведомление барберу
    barber_message = f"""
🔔 <b>НОВАЯ ЗАПИСЬ!</b>

🆔 <b>Номер:</b> <code>{booking.id}</code>

👤 <b>Клиент:</b> {data['name']}
📞 <b>Телефон:</b> {data['phone']}
🆔 <b>Telegram:</b> {data.get('username', 'не указан')}
📅 <b>Дата:</b> {data['date']}
🕐 <b>Время:</b> {data['time']}
💈 <b>Услуга:</b> {service_info['emoji']} {service_info['name']}
⏱ <b>Длительность:</b> {service_info['duration']} мин
💰 <b>Стоимость:</b> {service_info['price']}₽
    """
    
    try:
        await bot.send_message(
            chat_id=BARBER_CHAT_ID,
            text=barber_message,
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления барберу: {e}")
    
    await state.clear()
    await callback.answer("✅ Запись создана!")


@router.message(Command("my_bookings"))
async def cmd_my_bookings(message: Message):
    """Показать мои записи"""
    bookings = await BookingDAO.get_user_bookings(message.from_user.id)
    
    if not bookings:
        await message.answer(
            "📅 <b>У вас пока нет активных записей.</b>\n\n"
            "Используйте /book чтобы записаться.",
            parse_mode='HTML'
        )
        return
    
    keyboard = get_my_bookings_keyboard(bookings)
    
    text = "<b>📋 Ваши записи:</b>\n\n"
    
    for booking in bookings:
        text += f"🆔 <b>Номер:</b> <code>{booking.id}</code>\n"
        text += f"📅 {booking.booking_date} в {booking.booking_time}\n"
        text += f"💈 {booking.service_name}\n"
        text += f"💰 {booking.service_price}₽\n\n"
    
    text += "<i>Нажмите на номер записи, чтобы отменить её.</i>"
    
    await message.answer(text, reply_markup=keyboard, parse_mode='HTML')


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking_confirm(callback: CallbackQuery):
    """Подтверждение отмены записи"""
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    booking = await BookingDAO.get_by_id(booking_id)
    
    if not booking:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    
    keyboard = get_cancel_confirm_keyboard(booking_id)
    
    text = f"""
⚠️ <b>Вы уверены, что хотите отменить запись?</b>

🆔 <b>Номер:</b> <code>{booking.id}</code>
📅 <b>Дата:</b> {booking.booking_date}
🕐 <b>Время:</b> {booking.booking_time}
💈 <b>Услуга:</b> {booking.service_name}
    """
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_cancel_"))
async def confirm_cancel_booking(callback: CallbackQuery, bot: Bot):
    """Подтверждение отмены"""
    booking_id = int(callback.data.replace("confirm_cancel_", ""))
    booking = await BookingDAO.get_by_id(booking_id)
    
    if not booking:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    
    # Отменяем запись
    success = await BookingDAO.cancel(booking_id)
    
    if success:
        # Уведомляем клиента
        await callback.message.edit_text(
            f"✅ <b>Запись #{booking_id} успешно отменена.</b>\n\n"
            f"Для новой записи используйте /book",
            parse_mode='HTML'
        )
        
        # Уведомляем барбера
        barber_message = f"""
❌ <b>ОТМЕНА ЗАПИСИ</b>

🆔 <b>Номер:</b> <code>{booking.id}</code>
👤 <b>Клиент:</b> {booking.user_name}
📅 <b>Дата:</b> {booking.booking_date}
🕐 <b>Время:</b> {booking.booking_time}
💈 <b>Услуга:</b> {booking.service_name}
        """
        
        try:
            await bot.send_message(
                chat_id=BARBER_CHAT_ID,
                text=barber_message,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления барберу: {e}")
        
        await callback.answer("✅ Запись отменена")
    else:
        await callback.answer("❌ Ошибка отмены записи", show_alert=True)


@router.callback_query(F.data == "back_to_bookings")
async def back_to_bookings(callback: CallbackQuery):
    """Вернуться к списку записей"""
    bookings = await BookingDAO.get_user_bookings(callback.from_user.id)
    
    keyboard = get_my_bookings_keyboard(bookings)
    
    text = "<b>📋 Ваши записи:</b>\n\n"
    
    for booking in bookings:
        text += f"🆔 <b>Номер:</b> <code>{booking.id}</code>\n"
        text += f"📅 {booking.booking_date} в {booking.booking_time}\n"
        text += f"💈 {booking.service_name}\n"
        text += f"💰 {booking.service_price}₽\n\n"
    
    text += "<i>Нажмите на номер записи, чтобы отменить её.</i>"
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена процесса записи"""
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer("Нет активного процесса записи.")
        return
    
    await state.clear()
    await message.answer(
        "❌ <b>Процесс записи отменен.</b>\n\nДля новой записи используйте /book",
        parse_mode='HTML'
    )
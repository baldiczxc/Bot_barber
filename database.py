# database.py
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, BigInteger, DateTime, Boolean, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import DATABASE_URL


# База для моделей
class Base(DeclarativeBase):
    pass


# Модель пользователя
class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    
    def __repr__(self):
        return f"<User {self.full_name} (@{self.username})>"


# Модель записи
class Booking(Base):
    __tablename__ = "bookings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_name: Mapped[str] = mapped_column(String(255))
    user_phone: Mapped[str] = mapped_column(String(20))
    user_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    booking_date: Mapped[str] = mapped_column(String(10))  # DD.MM.YYYY
    booking_time: Mapped[str] = mapped_column(String(5))   # HH:MM
    
    service_type: Mapped[str] = mapped_column(String(50))
    service_name: Mapped[str] = mapped_column(String(255))
    service_price: Mapped[int] = mapped_column(Integer)
    service_duration: Mapped[int] = mapped_column(Integer)  # в минутах
    
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, completed, cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Комментарий барбера (опционально)
    barber_comment: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    def __repr__(self):
        return f"<Booking {self.user_name} - {self.booking_date} {self.booking_time}>"


# Модель для выходных дней барбера
class BarberDayOff(Base):
    __tablename__ = "barber_daysoff"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # DD.MM.YYYY
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<BarberDayOff {self.date}>"


# Создание движка и сессии
engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Инициализация базы данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Получение сессии базы данных"""
    async with async_session_maker() as session:
        return session


# CRUD операции для пользователей
class UserDAO:
    @staticmethod
    async def create_or_update(
        telegram_id: int,
        username: Optional[str],
        full_name: str,
        phone: str
    ) -> User:
        """Создать или обновить пользователя"""
        async with async_session_maker() as session:
            # Проверяем существование
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                # Обновляем данные
                user.username = username
                user.full_name = full_name
                user.phone = phone
            else:
                # Создаем нового
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    full_name=full_name,
                    phone=phone
                )
                session.add(user)
            
            await session.commit()
            await session.refresh(user)
            return user
    
    @staticmethod
    async def get_by_telegram_id(telegram_id: int) -> Optional[User]:
        """Получить пользователя по telegram_id"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()


# CRUD операции для записей
class BookingDAO:
    @staticmethod
    async def create(
        user_telegram_id: int,
        user_name: str,
        user_phone: str,
        user_username: Optional[str],
        booking_date: str,
        booking_time: str,
        service_type: str,
        service_name: str,
        service_price: int,
        service_duration: int
    ) -> Booking:
        """Создать запись"""
        async with async_session_maker() as session:
            booking = Booking(
                user_telegram_id=user_telegram_id,
                user_name=user_name,
                user_phone=user_phone,
                user_username=user_username,
                booking_date=booking_date,
                booking_time=booking_time,
                service_type=service_type,
                service_name=service_name,
                service_price=service_price,
                service_duration=service_duration
            )
            session.add(booking)
            await session.commit()
            await session.refresh(booking)
            return booking
    
    @staticmethod
    async def get_by_date_time(booking_date: str, booking_time: str) -> Optional[Booking]:
        """Проверить занято ли время"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Booking).where(
                    Booking.booking_date == booking_date,
                    Booking.booking_time == booking_time,
                    Booking.status == "active"
                )
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_date(booking_date: str) -> List[Booking]:
        """Получить все записи на определенную дату"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Booking).where(
                    Booking.booking_date == booking_date,
                    Booking.status == "active"
                ).order_by(Booking.booking_time)
            )
            return list(result.scalars().all())
    
    @staticmethod
    async def get_user_bookings(telegram_id: int, status: str = "active") -> List[Booking]:
        """Получить записи пользователя"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Booking).where(
                    Booking.user_telegram_id == telegram_id,
                    Booking.status == status
                ).order_by(Booking.booking_date, Booking.booking_time)
            )
            return list(result.scalars().all())
    
    @staticmethod
    async def get_by_id(booking_id: int) -> Optional[Booking]:
        """Получить запись по ID"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Booking).where(Booking.id == booking_id)
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def cancel(booking_id: int) -> bool:
        """Отменить запись"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Booking).where(Booking.id == booking_id)
            )
            booking = result.scalar_one_or_none()
            
            if booking:
                booking.status = "cancelled"
                await session.commit()
                return True
            return False
    
    @staticmethod
    async def get_all_active() -> List[Booking]:
        """Получить все активные записи"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Booking).where(
                    Booking.status == "active"
                ).order_by(Booking.booking_date, Booking.booking_time)
            )
            return list(result.scalars().all())


# CRUD операции для выходных дней
class BarberDayOffDAO:
    @staticmethod
    async def create(date: str, reason: Optional[str] = None) -> BarberDayOff:
        """Добавить выходной день"""
        async with async_session_maker() as session:
            day_off = BarberDayOff(date=date, reason=reason)
            session.add(day_off)
            await session.commit()
            await session.refresh(day_off)
            return day_off
    
    @staticmethod
    async def get_by_date(date: str) -> Optional[BarberDayOff]:
        """Получить выходной по дате"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(BarberDayOff).where(BarberDayOff.date == date)
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all() -> List[BarberDayOff]:
        """Получить все выходные дни"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(BarberDayOff).order_by(BarberDayOff.date)
            )
            return list(result.scalars().all())
    
    @staticmethod
    async def delete(date: str) -> bool:
        """Удалить выходной день"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(BarberDayOff).where(BarberDayOff.date == date)
            )
            day_off = result.scalar_one_or_none()
            
            if day_off:
                await session.delete(day_off)
                await session.commit()
                return True
            return False
    
    @staticmethod
    async def get_upcoming(limit: int = 30) -> List[BarberDayOff]:
        """Получить ближайшие выходные дни"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(BarberDayOff)
                .order_by(BarberDayOff.date)
                .limit(limit)
            )
            return list(result.scalars().all())
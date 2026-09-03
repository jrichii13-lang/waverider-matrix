import datetime
from enum import Enum
from sqlalchemy.pool import NullPool
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

class ExecutionMode(str, Enum):
    MANUAL = "MANUAL"
    FULLY_AUTO = "FULLY_AUTO"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"

class Strategy(Base):
    __tablename__ = 'strategies'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    execution_mode = Column(SQLEnum(ExecutionMode), default=ExecutionMode.MANUAL)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))
    signals = relationship("SignalAlert", back_populates="strategy")
    positions = relationship("Position", back_populates="strategy")

class SignalAlert(Base):
    __tablename__ = 'signals_alerts'
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id'), nullable=False)
    ticker = Column(String(10), nullable=False)
    option_type = Column(SQLEnum(OptionType), nullable=False)
    strike_price = Column(Float, nullable=False)
    expiration_date = Column(DateTime, nullable=False)
    entry_signal_price = Column(Float)
    is_executed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))
    strategy = relationship("Strategy", back_populates="signals")
    orders = relationship("Order", back_populates="signal")

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey('signals_alerts.id'), nullable=True)
    broker_order_id = Column(String(100), unique=True, nullable=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    quantity = Column(Integer, nullable=False)
    limit_price = Column(Float)
    filled_price = Column(Float)
    filled_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))
    signal = relationship("SignalAlert", back_populates="orders")
    position_legs = relationship("PositionLeg", back_populates="order")

class Position(Base):
    __tablename__ = 'positions'
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id'), nullable=False)
    ticker = Column(String(10), nullable=False)
    is_open = Column(Boolean, default=True)
    
    # --- P&L TRACKING COLUMNS ---
    entry_price = Column(Float, nullable=True) 
    realized_pnl = Column(Float, default=0.0)
    
    opened_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    closed_at = Column(DateTime, nullable=True)
    strategy = relationship("Strategy", back_populates="positions")
    legs = relationship("PositionLeg", back_populates="position")

class PositionLeg(Base):
    __tablename__ = 'position_legs'
    id = Column(Integer, primary_key=True)
    position_id = Column(Integer, ForeignKey('positions.id'), nullable=False)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    option_symbol = Column(String(50), nullable=False)
    ratio = Column(Integer, default=1)
    position = relationship("Position", back_populates="legs")
    order = relationship("Order", back_populates="position_legs")

def init_db(database_url="sqlite:///options_trading.db"):
    engine = create_engine(database_url, echo=False, poolclass=NullPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)

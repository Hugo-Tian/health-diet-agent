from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, JSON, UniqueConstraint, Boolean
from .db import Base, utcnow

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(254), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    revision = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class Session(Base):
    __tablename__ = 'sessions'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    csrf = Column(String(128), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

class Profile(Base):
    __tablename__ = 'profiles'
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    data = Column(JSON, nullable=False, default=dict)

class NutritionTarget(Base):
    __tablename__ = 'nutrition_targets'
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    data = Column(JSON, nullable=False)
    confirmed_at = Column(DateTime(timezone=True), default=utcnow)

class Food(Base):
    __tablename__ = 'foods'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    group = Column(String(30), nullable=False)
    state = Column(String(20), nullable=False)
    nutrients = Column(JSON, nullable=False)
    allergens = Column(JSON, nullable=False)
    tags = Column(JSON, nullable=False)
    source = Column(String(200), nullable=False)
    version = Column(String(40), nullable=False, default='demo-1')
    active = Column(Boolean, nullable=False, default=True)
    provenance = Column(JSON, nullable=False, default=dict)

class Portion(Base):
    __tablename__ = 'portions'
    id = Column(Integer, primary_key=True)
    food_id = Column(ForeignKey('foods.id', ondelete='CASCADE'), nullable=False)
    unit = Column(String(40), nullable=False)
    grams = Column(Float, nullable=False)
    source = Column(String(100), default='演示家用量，请以称重为准')

class DailyPlan(Base):
    __tablename__ = 'daily_plans'
    __table_args__ = (UniqueConstraint('user_id', 'local_date', 'version'),)
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    local_date = Column(Date, nullable=False)
    version = Column(Integer, nullable=False)
    based_on_revision = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class MealPlanItem(Base):
    __tablename__ = 'meal_plan_items'
    id = Column(Integer, primary_key=True)
    plan_id = Column(ForeignKey('daily_plans.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    meal = Column(String(20), nullable=False)
    snapshot = Column(JSON, nullable=False)

class DailyState(Base):
    __tablename__ = 'daily_states'
    __table_args__ = (UniqueConstraint('user_id', 'local_date'),)
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    local_date = Column(Date, nullable=False)
    active_plan_id = Column(Integer, nullable=False)

class FoodLog(Base):
    __tablename__ = 'food_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    local_date = Column(Date, nullable=False)
    eaten_at = Column(DateTime(timezone=True), nullable=False)
    meal = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)
    finished = Column(String(20), nullable=False)
    note = Column(String(500), default='')

class FoodLogItem(Base):
    __tablename__ = 'food_log_items'
    id = Column(Integer, primary_key=True)
    log_id = Column(ForeignKey('food_logs.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    snapshot = Column(JSON, nullable=False)

class AdjustmentProposal(Base):
    __tablename__ = 'adjustment_proposals'
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    local_date = Column(Date, nullable=False)
    base_plan_id = Column(Integer, nullable=True)
    base_data_revision = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)
    reason = Column(String(500), nullable=False)
    status = Column(String(20), default='pending', nullable=False)
    result_plan_id = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    confirmed_at = Column(DateTime(timezone=True))
    batch_id = Column(String(36), nullable=True, index=True)

class ChatTurn(Base):
    __tablename__ = 'chat_turns'
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    local_date = Column(Date, nullable=False)
    question = Column(String(2000), nullable=False)
    answer = Column(JSON, nullable=False)
    request_id = Column(String(36), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('user_id','request_id'),)

class Feedback(Base):
    __tablename__ = 'feedback'
    __table_args__ = (UniqueConstraint('user_id', 'local_date', 'revision'),)
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    local_date = Column(Date, nullable=False)
    revision = Column(Integer, nullable=False)
    data = Column(JSON, nullable=False)

class WeightLog(Base):
    __tablename__ = 'weight_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    local_date = Column(Date, nullable=False)
    kg = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

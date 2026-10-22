from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict, field_validator

Meal = Literal['早餐', '午餐', '晚餐', '加餐']

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Credentials(Strict):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=10, max_length=128)

class ProfileData(Strict):
    adult: bool = False
    age: int | None = Field(None, ge=1, le=120)
    height_cm: float | None = Field(None, ge=80, le=250)
    weight_kg: float | None = Field(None, ge=20, le=350)
    timezone: str = 'Asia/Shanghai'
    goal: Literal['均衡饮食', '体重管理', '增肌支持'] = '均衡饮食'
    goal_confirmed: bool = False
    activity: Literal['久坐', '轻活动', '较活跃'] = '轻活动'
    exercise: str = Field('', max_length=200)
    budget: float | None = Field(None, ge=0, le=10000)
    dining: Literal['食堂', '外卖', '做饭'] = '食堂'
    equipment: str = Field('', max_length=200)
    prep_minutes: int = Field(20, ge=0, le=300)
    meal_times: str = Field('08:00 / 12:00 / 18:30', max_length=100)
    diet: Literal['无', '纯素', '蛋奶素'] = '无'
    allergens: list[str] = Field(default_factory=list, max_length=30)
    exclusions: list[str] = Field(default_factory=list, max_length=30)
    preferences: str = Field('', max_length=300)
    special: list[Literal['孕哺期', '治疗性饮食', '进食障碍相关']] = Field(default_factory=list, max_length=3)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try: ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError): raise ValueError('请提供有效 IANA 时区')
        return value

    @field_validator('allergens', 'exclusions')
    @classmethod
    def valid_terms(cls, values):
        if any(not x.strip() or len(x) > 40 for x in values): raise ValueError('限制项须为 1–40 字')
        # Exact absence markers only; never discard unknown/allergy names.
        # Applied on reads as well as writes so existing ['无'] profiles work.
        return list(dict.fromkeys(x.strip() for x in values if x.strip().lower() not in {'无','没有','none','无过敏','无过敏原','无忌口','没有过敏','没有忌口'}))

class ProfileUpdate(Strict):
    revision: int
    profile: ProfileData

class DateRequest(Strict):
    date: date

class PlanRequest(DateRequest):
    revision: int

class Replacement(PlanRequest):
    meal: Meal = '晚餐'
    food_id: int | None = None
    replace_food_id: int | None = None

class LogItemInput(Strict):
    food_id: int | None = None
    name: str = Field('', max_length=100)
    grams: float | None = Field(None, gt=0, le=3000)

class LogInput(Strict):
    revision: int
    eaten_at: datetime
    meal: Meal
    status: Literal['pending', 'confirmed'] = 'pending'
    finished: Literal['yes', 'partial', 'unknown'] = 'unknown'
    note: str = Field('', max_length=500)
    items: list[LogItemInput] = Field(min_length=1, max_length=30)

    @field_validator('eaten_at')
    @classmethod
    def aware_time(cls, v):
        if v.utcoffset() is None: raise ValueError('用餐时间必须包含时区偏移')
        return v

class TargetInput(Strict):
    revision: int
    lower: int = Field(ge=1200, le=5000)
    upper: int = Field(ge=1200, le=5000)
    confirmed: bool = False

class MessageInput(DateRequest):
    message: str = Field(min_length=1, max_length=2000)
    share_context: bool = False
    request_id: str = Field(default_factory=lambda:str(uuid4()),min_length=8,max_length=36,pattern=r'^[a-zA-Z0-9-]+$')

class PhotoInput(Strict):
    revision: int
    request_id: str = Field(default_factory=lambda:str(uuid4()),min_length=8,max_length=36,pattern=r'^[a-zA-Z0-9-]+$')
    image_data: str = Field(min_length=40,max_length=5_600_000)
    message: str = Field('',max_length=1000)
    eaten_at: datetime
    meal: Meal
    share_context: bool = False

    @field_validator('eaten_at')
    @classmethod
    def aware_time(cls,v):
        if v.utcoffset() is None: raise ValueError('用餐时间必须包含时区')
        return v

class WeightInput(PlanRequest):
    kg: float = Field(ge=20, le=350)

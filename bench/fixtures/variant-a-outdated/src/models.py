from datetime import datetime
from typing import Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel, validator, root_validator
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()
T = TypeVar("T")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    email = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None

    class Config:
        str_strip_whitespace = True
        json_encoders = {datetime: lambda v: v.isoformat()}

    @validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Name cannot be empty")
        return v


class UserResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None

    @root_validator
    @classmethod
    def check_consistency(cls, values):
        return values

    def to_dict(self) -> dict:
        return self.dict()

    @classmethod
    def from_orm(cls, obj):
        return cls.parse_obj(obj.__dict__)


class Registry(Generic[T]):
    def __init__(self) -> None:
        self._items: Dict[str, T] = {}

    def add(self, key: str, value: T) -> None:
        self._items[key] = value

    def get(self, key: str) -> Union[T, None]:
        return self._items.get(key)

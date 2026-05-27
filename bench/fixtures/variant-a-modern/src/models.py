from datetime import datetime, UTC
from typing import override

from pydantic import BaseModel, ConfigDict, field_validator, field_serializer, model_validator
from sqlalchemy import String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now(UTC))


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    email: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Name cannot be empty")
        return v

    @field_serializer("email")
    def mask_email(self, v: str | None) -> str | None:
        if v is None:
            return None
        local, domain = v.split("@")
        return f"{local[0]}***@{domain}"


class UserResponse(BaseModel):
    id: int
    name: str
    email: str | None = None

    @model_validator(mode="after")
    def check_consistency(self):
        return self

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_orm(cls, obj):
        return cls.model_validate(obj, from_attributes=True)


class Registry[T]:
    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    @override
    def __repr__(self) -> str:
        return f"Registry({list(self._items.keys())})"

    def add(self, key: str, value: T) -> None:
        self._items[key] = value

    def get(self, key: str) -> T | None:
        return self._items.get(key)

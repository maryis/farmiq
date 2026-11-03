from __future__ import annotations

import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    display_name: str = Field(min_length=2, max_length=160)
    farm_name: str = Field(min_length=2, max_length=160)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    farm_id: uuid.UUID


class FeedbackRequest(BaseModel):
    outcome: str = Field(pattern="^(confirmed|dismissed|not_sure|resolved)$")
    note: str | None = None


class OptimizeRequest(BaseModel):
    milk_price_eur_per_kg: float = Field(default=0.47, ge=0.1, le=1.5)
    horizon_days: int = Field(default=7, ge=1, le=30)
    persist: bool = False
    price_overrides: dict[str, float] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    farm_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="auto", pattern="^(auto|en|nl)$")


class ChatSource(BaseModel):
    title: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    language: str
    sources: list[ChatSource] = []
    tool_context: dict = {}

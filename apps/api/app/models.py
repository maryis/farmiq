from __future__ import annotations

import uuid
from datetime import datetime

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # keeps lightweight tooling usable; production installs pgvector
    Vector = None
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))


class Farm(TimestampMixin, Base):
    __tablename__ = "farms"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Amsterdam")
    country_code: Mapped[str] = mapped_column(String(2), default="NL")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FarmMembership(TimestampMixin, Base):
    __tablename__ = "farm_memberships"
    __table_args__ = (UniqueConstraint("user_id", "farm_id", name="uq_user_farm"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="owner")


class AnimalGroup(TimestampMixin, Base):
    __tablename__ = "animal_groups"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    stage: Mapped[str] = mapped_column(String(40))
    target_dmi_kg: Mapped[float] = mapped_column(Float)
    target_vem: Mapped[float] = mapped_column(Float)
    target_dve_g: Mapped[float] = mapped_column(Float)
    min_ndf_g: Mapped[float] = mapped_column(Float)
    oeb_min_g: Mapped[float] = mapped_column(Float, default=-200)


class Animal(TimestampMixin, Base):
    __tablename__ = "animals"
    __table_args__ = (UniqueConstraint("farm_id", "external_id", name="uq_farm_animal_external"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("animal_groups.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parity: Mapped[int] = mapped_column(Integer, default=1)
    days_in_milk: Mapped[int] = mapped_column(Integer, default=0)
    body_condition_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class SensorObservation(TimestampMixin, Base):
    __tablename__ = "sensor_observations"
    __table_args__ = (
        UniqueConstraint("animal_id", "kind", "observed_at", "source", name="uq_sensor_event"),
        Index("ix_sensor_farm_kind_time", "farm_id", "kind", "observed_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    animal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(40), default="demo")
    source_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class HealthRisk(TimestampMixin, Base):
    __tablename__ = "health_risks"
    __table_args__ = (Index("ix_health_farm_active_score", "farm_id", "active", "score"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    animal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    risk_type: Mapped[str] = mapped_column(String(40), index=True)
    score: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(80), default="rules-v1")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class HealthFeedback(TimestampMixin, Base):
    __tablename__ = "health_feedback"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    risk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("health_risks.id"), index=True)
    outcome: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeedIngredient(TimestampMixin, Base):
    __tablename__ = "feed_ingredients"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    dry_matter_fraction: Mapped[float] = mapped_column(Float)
    vem_per_kg_dm: Mapped[float] = mapped_column(Float)
    dve_g_per_kg_dm: Mapped[float] = mapped_column(Float)
    oeb_g_per_kg_dm: Mapped[float] = mapped_column(Float)
    ndf_g_per_kg_dm: Mapped[float] = mapped_column(Float)
    price_eur_per_kg_dm: Mapped[float] = mapped_column(Float)
    min_kg_dm: Mapped[float] = mapped_column(Float, default=0)
    max_kg_dm: Mapped[float] = mapped_column(Float, default=99)
    source: Mapped[str] = mapped_column(String(80), default="farm-analysis")


class FeedInventory(TimestampMixin, Base):
    __tablename__ = "feed_inventory"
    __table_args__ = (UniqueConstraint("farm_id", "ingredient_id", name="uq_farm_inventory_ingredient"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("feed_ingredients.id"), index=True)
    stock_kg_as_fed: Mapped[float] = mapped_column(Float)
    daily_use_kg_as_fed: Mapped[float] = mapped_column(Float)
    reorder_threshold_days: Mapped[float] = mapped_column(Float, default=10)


class RationPlan(TimestampMixin, Base):
    __tablename__ = "ration_plans"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("animal_groups.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="scenario", index=True)
    milk_price_eur_per_kg: Mapped[float] = mapped_column(Float, default=0.47)
    cost_eur_per_cow_day: Mapped[float] = mapped_column(Float, default=0)
    nutrition_summary: Mapped[dict] = mapped_column(JSON, default=dict)


class RationItem(TimestampMixin, Base):
    __tablename__ = "ration_items"
    __table_args__ = (UniqueConstraint("plan_id", "ingredient_id", name="uq_plan_ingredient"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ration_plans.id"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("feed_ingredients.id"), index=True)
    kg_dm_per_cow_day: Mapped[float] = mapped_column(Float)


class Integration(TimestampMixin, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("farm_id", "provider", name="uq_farm_provider"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(32), default="not_connected")
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SyncCursor(TimestampMixin, Base):
    __tablename__ = "sync_cursors"
    __table_args__ = (UniqueConstraint("integration_id", "stream", name="uq_sync_stream"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id"), index=True)
    stream: Mapped[str] = mapped_column(String(80))
    watermark: Mapped[str | None] = mapped_column(String(255), nullable=True)


class KnowledgeChunk(TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(240))
    source_url: Mapped[str] = mapped_column(String(600))
    language: Mapped[str] = mapped_column(String(8), default="en")
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    _embedding_type = JSON().with_variant(Vector(1024), "postgresql") if Vector else JSON()
    embedding: Mapped[list | None] = mapped_column(_embedding_type, nullable=True)

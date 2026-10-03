"""Operational entities added by the merge: hospital network, hospital pre-alerts and dispatch assignments."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    # Occupancy ratios 0..1 (share of capacity in use). Updated by the hospital desk endpoint.
    icu_load: Mapped[float] = mapped_column(Float, default=0.4)
    er_load: Mapped[float] = mapped_column(Float, default=0.4)
    oxygen_load: Mapped[float] = mapped_column(Float, default=0.3)
    specialties: Mapped[list] = mapped_column(JSON, default=list)
    helipad: Mapped[bool] = mapped_column(Boolean, default=False)
    accepting: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(40), default="demo_seed")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HospitalAlert(Base):
    __tablename__ = "hospital_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    incident_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stage: Mapped[str] = mapped_column(String(24), default="pre_alert")  # pre_alert | en_route | arrived
    priority: Mapped[str] = mapped_column(String(16), default="high")
    condition: Mapped[str] = mapped_column(String(80), default="unknown")
    eta_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DispatchAssignment(Base):
    __tablename__ = "dispatch_assignments"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    hospital_id: Mapped[str | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="assigned")  # assigned | completed | cancelled
    plan: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

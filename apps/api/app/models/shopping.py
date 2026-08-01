from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.identity import new_id


class ShoppingList(TimestampMixin, Base):
    __tablename__ = "shopping_lists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    store: Mapped[str | None] = mapped_column(String(120), index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    responsible_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="no_date", index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[ShoppingItem]] = relationship(
        back_populates="shopping_list", cascade="all, delete-orphan"
    )


class ShoppingItem(TimestampMixin, Base):
    __tablename__ = "shopping_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    list_id: Mapped[str] = mapped_column(
        ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), default="шт.", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="другое", index=True)
    note: Mapped[str | None] = mapped_column(String(500))
    added_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    recipient_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    purchased: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    photo_id: Mapped[str | None] = mapped_column(String(36))
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    store: Mapped[str | None] = mapped_column(String(120))
    proposal_status: Mapped[str] = mapped_column(String(12), default="accepted", index=True)
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_operation_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    shopping_list: Mapped[ShoppingList] = relationship(back_populates="items")

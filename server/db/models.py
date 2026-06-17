"""
SQLAlchemy ORM models for the Account agent's data (Phase 2).

These are the *tables* — the shape of what lives in Postgres. They are NOT what
the agent/LLM sees: the tools (Phase 2, step 5) convert rows into small Pydantic
objects so the model only ever receives the fields we choose to expose. Keeping
those two layers separate is the whole "don't let the model see data it
shouldn't" lesson.

Style note: this is SQLAlchemy 2.0 syntax — `Mapped[...]` type annotations plus
`mapped_column(...)`, which replaces the old `Column(...)` + `declarative_base()`
style you'll see in older tutorials.

Relationships here are one-to-many: 1 customer -> N orders, 1 customer -> N
subscriptions. The "many" side is whichever table holds the ForeignKey (orders,
subscriptions); a `Mapped[list[...]]` is the collection ("many") end and a plain
`Mapped["Customer"]` is the scalar ("one") end.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """All models inherit from this; it carries the shared metadata/registry."""
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # email is how the agent looks a customer up, so it's unique + indexed.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # relationship() is the ORM-level link; the real DB constraint is the
    # ForeignKey on the child tables below. back_populates keeps both sides in
    # sync. cascade="all, delete-orphan": deleting a customer deletes their
    # orders/subscriptions, and detaching a child from the collection deletes it.
    orders: Mapped[list["Order"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    # Free-text-ish status. A real system would use an enum/check constraint;
    # a plain string keeps the learning focus on querying, not schema design.
    status: Mapped[str] = mapped_column(String(32))  # pending|shipped|delivered|cancelled|refunded
    item: Mapped[str] = mapped_column(String(200))
    # Money as Numeric(10,2) -> Python Decimal. Never float for currency.
    # Stores up to 10 digits, up to 2 decimal places i.e 99999999.99
    total_amount: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer: Mapped["Customer"] = relationship(back_populates="orders")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    plan: Mapped[str] = mapped_column(String(32))    # free|pro|enterprise
    status: Mapped[str] = mapped_column(String(32))  # active|past_due|canceled
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer: Mapped["Customer"] = relationship(back_populates="subscriptions")

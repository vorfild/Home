from __future__ import annotations

import asyncio
import json
import smtplib
from datetime import UTC, datetime, time, timedelta
from email.message import EmailMessage
from importlib import import_module
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.home import Equipment, MaintenancePlan, Meter
from app.models.identity import Household, User
from app.models.preferences import Notification, PushSubscription, UserPreference
from app.models.shopping import ShoppingList
from app.models.storage import StorageItem
from app.models.tasks import TaskAssignment, TaskDefinition, TaskInstance
from app.schemas.settings import EVENT_TYPES


async def preference_for(db: AsyncSession, user_id: str) -> UserPreference:
    item = await db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if item is None:
        item = UserPreference(
            user_id=user_id,
            event_rules={key: True for key in EVENT_TYPES},
        )
        db.add(item)
        await db.flush()
    return item


async def create_notification(
    db: AsyncSession,
    *,
    household_id: str,
    user_id: str,
    event_type: str,
    title: str,
    body: str,
    source_type: str,
    source_id: str,
    marker: str,
) -> bool:
    preference = await preference_for(db, user_id)
    if not preference.event_rules.get(event_type, True):
        return False
    dedupe = f"{user_id}:{event_type}:{source_type}:{source_id}:{marker}"
    if await db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe)):
        return False
    db.add(
        Notification(
            household_id=household_id,
            user_id=user_id,
            event_type=event_type,
            title=title,
            body=body,
            source_type=source_type,
            source_id=source_id,
            dedupe_key=dedupe,
        )
    )
    return True


async def generate_due_notifications(db: AsyncSession, *, moment: datetime | None = None) -> int:
    now = moment or datetime.now(UTC)
    households = list(await db.scalars(select(Household)))
    created = 0
    for house in households:
        users = list(
            await db.scalars(
                select(User).where(User.household_id == house.id, User.is_active.is_(True))
            )
        )
        if not users:
            continue
        user_ids = [user.id for user in users]
        preferences = {user.id: await preference_for(db, user.id) for user in users}
        max_ahead = max((item.reminder_minutes for item in preferences.values()), default=60)
        task_rows = list(
            await db.scalars(
                select(TaskInstance)
                .join(TaskDefinition)
                .where(
                    TaskDefinition.household_id == house.id,
                    TaskInstance.status.in_(["open", "rejected"]),
                    TaskInstance.due_at.is_not(None),
                    TaskInstance.due_at <= now + timedelta(minutes=max_ahead),
                )
            )
        )
        for instance in task_rows:
            task = await db.scalar(
                select(TaskDefinition).where(TaskDefinition.id == instance.task_id)
            )
            if task is None:
                continue
            recipients: list[str]
            if instance.assignee_id:
                recipients = [instance.assignee_id]
            else:
                recipients = (
                    list(
                        await db.scalars(
                            select(TaskAssignment.user_id).where(TaskAssignment.task_id == task.id)
                        )
                    )
                    or user_ids
                )
            due_at = instance.due_at
            if due_at is not None and due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=UTC)
            event = "task_overdue" if due_at and due_at < now else "task_due"
            for user_id in set(recipients):
                preference = preferences.get(user_id)
                if preference is None or due_at is None:
                    continue
                if event == "task_due" and due_at > now + timedelta(
                    minutes=preference.reminder_minutes
                ):
                    continue
                created += int(
                    await create_notification(
                        db,
                        household_id=house.id,
                        user_id=user_id,
                        event_type=event,
                        title=task.title,
                        body="Срок дела наступил"
                        if event == "task_overdue"
                        else "Срок дела приближается",
                        source_type="task",
                        source_id=instance.id,
                        marker=due_at.isoformat(),
                    )
                )

        local_today = now.astimezone(ZoneInfo(house.timezone)).date()
        shopping = list(
            await db.scalars(
                select(ShoppingList).where(
                    ShoppingList.household_id == house.id,
                    ShoppingList.status.in_(["planned", "in_progress"]),
                    ShoppingList.scheduled_at
                    >= datetime.combine(local_today, time.min, ZoneInfo(house.timezone)).astimezone(
                        UTC
                    ),
                    ShoppingList.scheduled_at
                    < datetime.combine(
                        local_today + timedelta(days=1), time.min, ZoneInfo(house.timezone)
                    ).astimezone(UTC),
                )
            )
        )
        maintenance = list(
            await db.scalars(
                select(MaintenancePlan).where(
                    MaintenancePlan.household_id == house.id,
                    MaintenancePlan.is_active.is_(True),
                    MaintenancePlan.next_on <= local_today,
                )
            )
        )
        storage = list(
            await db.scalars(
                select(StorageItem).where(
                    StorageItem.household_id == house.id,
                    StorageItem.review_status == "decision_required",
                )
            )
        )
        warranties = list(
            await db.scalars(
                select(Equipment).where(
                    Equipment.household_id == house.id,
                    Equipment.warranty_until >= local_today,
                    Equipment.warranty_until <= local_today + timedelta(days=30),
                )
            )
        )
        meters: list[Meter] = []
        if house.meters_enabled and house.module_settings.get("meters", True):
            meters = list(
                await db.scalars(
                    select(Meter).where(
                        Meter.household_id == house.id,
                        Meter.is_active.is_(True),
                        Meter.next_submission_on <= local_today,
                    )
                )
            )
        common: list[tuple[str, str, str, str, str]] = []
        common += [
            ("shopping_today", item.title, "Сегодня запланированы покупки", "shopping", item.id)
            for item in shopping
        ]
        common += [
            ("maintenance_due", item.title, "Наступил срок обслуживания", "maintenance", item.id)
            for item in maintenance
        ]
        common += [
            ("storage_review", item.name, "Истёк таймер хранения", "storage", item.id)
            for item in storage
        ]
        common += [
            (
                "warranty_expiring",
                item.name or "Оборудование",
                "Скоро закончится гарантия",
                "warranty",
                item.id,
            )
            for item in warranties
        ]
        common += [
            ("meter_due", item.meter_type, "Пора передать показания", "meter", item.id)
            for item in meters
        ]
        for event, title, body, source, source_id in common:
            for user in users:
                created += int(
                    await create_notification(
                        db,
                        household_id=house.id,
                        user_id=user.id,
                        event_type=event,
                        title=title,
                        body=body,
                        source_type=source,
                        source_id=source_id,
                        marker=local_today.isoformat(),
                    )
                )
    return created


def in_quiet_hours(preference: UserPreference, local_now: datetime) -> bool:
    if preference.quiet_start is None or preference.quiet_end is None:
        return False
    value = local_now.time().replace(tzinfo=None)
    if preference.quiet_start <= preference.quiet_end:
        return preference.quiet_start <= value < preference.quiet_end
    return value >= preference.quiet_start or value < preference.quiet_end


def _send_email(settings: Any, address: str, notification: Notification) -> None:
    message = EmailMessage()
    message["Subject"] = notification.title
    message["From"] = settings.smtp_from
    message["To"] = address
    message.set_content(notification.body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


def _send_push(settings: Any, subscription: PushSubscription, notification: Notification) -> None:
    module = import_module("pywebpush")
    module.webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=json.dumps({"title": notification.title, "body": notification.body}),
        vapid_private_key=settings.vapid_private_key.get_secret_value(),
        vapid_claims={"sub": settings.vapid_subject},
        ttl=60 * 60,
    )


async def dispatch_notifications(db: AsyncSession, *, moment: datetime | None = None) -> int:
    now = moment or datetime.now(UTC)
    settings = get_settings()
    notifications = list(
        await db.scalars(
            select(Notification).where(
                or_(Notification.push_sent_at.is_(None), Notification.email_sent_at.is_(None))
            )
        )
    )
    sent = 0
    for item in notifications:
        preference = await preference_for(db, item.user_id)
        house = await db.scalar(select(Household).where(Household.id == item.household_id))
        if house is None or in_quiet_hours(preference, now.astimezone(ZoneInfo(house.timezone))):
            continue
        errors: list[str] = []
        if preference.channels.get("email") and item.email_sent_at is None:
            if settings.smtp_host and settings.smtp_from and preference.email:
                try:
                    await asyncio.to_thread(_send_email, settings, preference.email, item)
                    item.email_sent_at = now
                    sent += 1
                except Exception as exc:
                    errors.append(f"email: {type(exc).__name__}")
            else:
                item.email_sent_at = now
        elif item.email_sent_at is None:
            item.email_sent_at = now
        if preference.channels.get("push") and item.push_sent_at is None:
            subscriptions = list(
                await db.scalars(
                    select(PushSubscription).where(
                        PushSubscription.user_id == item.user_id,
                        PushSubscription.is_active.is_(True),
                    )
                )
            )
            if settings.vapid_private_key.get_secret_value() and subscriptions:
                for subscription in subscriptions:
                    try:
                        await asyncio.to_thread(_send_push, settings, subscription, item)
                        subscription.failed_attempts = 0
                        sent += 1
                    except Exception as exc:
                        subscription.failed_attempts += 1
                        if subscription.failed_attempts >= 3:
                            subscription.is_active = False
                        errors.append(f"push: {type(exc).__name__}")
                if not errors:
                    item.push_sent_at = now
            else:
                item.push_sent_at = now
        elif item.push_sent_at is None:
            item.push_sent_at = now
        item.delivery_error = "; ".join(errors)[:300] or None
    return sent

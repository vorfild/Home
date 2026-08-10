from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lifecycle import Category

DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "task": ["уборка", "готовка", "стирка", "питомцы", "обслуживание", "другое"],
    "shopping": ["продукты", "хозяйственное", "аптека", "одежда", "другое"],
    "storage": [
        "одежда",
        "инструменты",
        "техника",
        "туризм и поездки",
        "документы",
        "сезонное",
        "другое",
    ],
}


def seed_default_categories(db: AsyncSession, household_id: str) -> None:
    for domain, names in DEFAULT_CATEGORIES.items():
        for position, name in enumerate(names):
            db.add(
                Category(
                    household_id=household_id,
                    domain=domain,
                    name=name,
                    sort_order=position,
                    color="#5E7FA3",
                    icon="tag",
                    is_active=True,
                    is_default=True,
                )
            )

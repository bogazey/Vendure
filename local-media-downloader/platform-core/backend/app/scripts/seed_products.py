"""Idempotent CLI seed for the initial product registry (mission-brief
section 7). Never runs automatically — an explicit operator action, same
posture as Loady's `promote_admin` script.

Usage: python -m app.scripts.seed_products
"""
from __future__ import annotations

from app.database.db import get_session_factory
from app.database.models import Product
from app.models.enums import ProductStatus

_PRODUCTS = [
    ("loady", "Loady", "loady.cc", ProductStatus.LIVE),
    ("gamey", "Gamey", "gamey.cc", ProductStatus.PLANNED),
    ("filey", "Filey", "filey.cc", ProductStatus.PLANNED),
    ("pixly", "Pixly", "pixly.cc", ProductStatus.PLANNED),
    ("aidy", "Aidy", "aidy.cc", ProductStatus.PLANNED),
    ("linky", "Linky", "linky.cc", ProductStatus.PLANNED),
    ("sendy", "Sendy", "sendy.cc", ProductStatus.PLANNED),
    ("convy", "Convy", "convy.cc", ProductStatus.PLANNED),
    ("civy", "Civy", "civy.cc", ProductStatus.PLANNED),
    ("crafty", "Crafty", "crafty.cc", ProductStatus.PLANNED),
]


def main() -> None:
    session = get_session_factory()()
    try:
        created = 0
        for product_id, name, domain, status in _PRODUCTS:
            if session.get(Product, product_id) is not None:
                continue
            session.add(Product(id=product_id, name=name, domain=domain, status=status.value))
            created += 1
        session.commit()
        print(f"Seeded {created} new product(s); {len(_PRODUCTS) - created} already existed.")
    finally:
        session.close()


if __name__ == "__main__":
    main()

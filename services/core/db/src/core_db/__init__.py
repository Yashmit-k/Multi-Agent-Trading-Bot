"""Persistence boundary. Other services use repositories, not ORM models."""

from core_db.repository import CoreRepository

__all__ = ["CoreRepository"]

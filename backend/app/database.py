"""Compatibility facade for the Chapter 4 campaign-data component."""

from system_components.data_management_layer.campaign_data.database import Base, DATABASE_URL, SessionLocal, engine

__all__ = ["Base", "DATABASE_URL", "SessionLocal", "engine"]

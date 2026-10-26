"""Base platform class for job scrapers."""

from abc import ABC, abstractmethod
from typing import Any


class BasePlatform(ABC):
    """Abstract base class for platform-specific scrapers."""

    @abstractmethod
    def fetch_jobs(self, site_config: dict[str, Any], max_results: int | None = None) -> list[dict[str, Any]]:
        """Fetch jobs from the platform."""
        pass

    @abstractmethod
    def normalize_job(self, raw_job: dict[str, Any], site_config: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw job to the canonical schema."""
        pass

"""Base types shared by all Pulse Scout module scanners."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ScanResult:
    module_id: str
    module_label: str
    items: list[dict]
    error: str | None = None


class BaseScanner(ABC):
    MODULE_ID: str
    MODULE_LABEL: str

    @abstractmethod
    def scan(self, days: int) -> ScanResult:
        """Run the scan for the given time window.

        Args:
            days: Number of days to look back. 0 means no filter.

        Returns:
            ScanResult with collected items or error message.
        """
        ...

"""Billing port (FR-48..52): Pro checkout and the customer portal."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ProPlan(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass(frozen=True)
class BillingCustomer:
    user_id: UUID
    email: str


@dataclass(frozen=True)
class CheckoutSession:
    session_id: str
    url: str


@dataclass(frozen=True)
class PortalSession:
    url: str


class BillingPort(ABC):
    @abstractmethod
    def create_checkout(
        self, customer: BillingCustomer, plan: ProPlan, *, success_url: str, cancel_url: str
    ) -> CheckoutSession: ...

    @abstractmethod
    def create_portal_session(self, customer_ref: str, *, return_url: str) -> PortalSession: ...

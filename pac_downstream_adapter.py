from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AdapterClass(str, Enum):
    A = "A"
    B = "B"
    C = "C"


@dataclass(frozen=True)
class AdapterCapabilities:
    adapter_class: AdapterClass
    native_idempotency: bool
    authoritative_reconciliation: bool
    authoritative_not_found: bool
    minimum_observation_seconds: int = 0
    eventual_consistency_bound_seconds: int = 0
    original_request_can_complete_late: bool = True

    def __post_init__(self) -> None:
        if self.minimum_observation_seconds < 0:
            raise ValueError("minimum_observation_seconds must be non-negative")
        if self.eventual_consistency_bound_seconds < 0:
            raise ValueError("eventual_consistency_bound_seconds must be non-negative")

        if self.adapter_class is AdapterClass.A and not self.native_idempotency:
            raise ValueError("Class A requires native idempotency")
        if self.adapter_class is AdapterClass.B:
            if self.native_idempotency:
                raise ValueError("Class B must not claim native idempotency")
            if not self.authoritative_reconciliation:
                raise ValueError("Class B requires authoritative reconciliation")
        if self.adapter_class is AdapterClass.C:
            if self.native_idempotency or self.authoritative_reconciliation:
                raise ValueError("Class C cannot claim native idempotency or authoritative reconciliation")
            if self.authoritative_not_found:
                raise ValueError("Class C cannot claim authoritative NOT_FOUND")

        if self.authoritative_not_found and not self.authoritative_reconciliation:
            raise ValueError("authoritative NOT_FOUND requires authoritative reconciliation")


@dataclass(frozen=True)
class NotFoundDecision:
    redispatch_eligible: bool
    reason: str


def evaluate_authoritative_not_found(
    capabilities: AdapterCapabilities,
    *,
    observation_age_seconds: int,
) -> NotFoundDecision:
    if observation_age_seconds < 0:
        return NotFoundDecision(False, "invalid_observation_age")

    if capabilities.adapter_class is AdapterClass.C:
        return NotFoundDecision(False, "class_c_never_auto_redispatches_not_found")

    if not capabilities.authoritative_not_found:
        return NotFoundDecision(False, "not_found_is_not_authoritative")

    required_age = max(
        capabilities.minimum_observation_seconds,
        capabilities.eventual_consistency_bound_seconds,
    )
    if observation_age_seconds < required_age:
        return NotFoundDecision(False, "authoritative_observation_window_not_elapsed")

    if capabilities.original_request_can_complete_late:
        return NotFoundDecision(False, "original_request_can_complete_late")

    if capabilities.adapter_class is AdapterClass.A:
        if not capabilities.native_idempotency:
            return NotFoundDecision(False, "native_idempotency_not_available")
        return NotFoundDecision(True, "class_a_idempotent_redispatch_eligible")

    if capabilities.adapter_class is AdapterClass.B:
        return NotFoundDecision(True, "class_b_authoritative_absence_redispatch_eligible")

    return NotFoundDecision(False, "unsupported_adapter_class")

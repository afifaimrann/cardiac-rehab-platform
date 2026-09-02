"""Persist risk flags raised by the rule engine."""
from __future__ import annotations

import logging
from typing import List, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical import RiskFlag
from app.models.enums import FlagSource
from app.models.user import PatientProfile
from app.services.risk_rules import RuleResult

logger = logging.getLogger("cardiac.flags")


async def persist_flags(
    db: AsyncSession,
    profile: PatientProfile,
    source_type: FlagSource,
    source_id: str,
    results: Sequence[RuleResult],
) -> List[RiskFlag]:
    """Create a RiskFlag row per triggered rule.

    Caller commits. Flags are written in the same transaction as the record that
    triggered them, so a reading can never be stored without its flag.
    """
    flags = [
        RiskFlag(
            patient_id=profile.id,
            source_type=source_type,
            source_id=source_id,
            rule_code=r.rule_code,
            severity=r.severity,
            message=r.message,
        )
        for r in results
    ]
    for flag in flags:
        db.add(flag)
    if flags:
        logger.info(
            "Raised %d flag(s) for patient %s: %s",
            len(flags), profile.id, ", ".join(f.rule_code for f in flags),
        )
    return flags

"""Rule-based risk evaluation for patient-submitted data.

Deliberately rules, not a model: a cardiac rehab programme needs decisions a
clinician can read, audit and overrule, and every flag here can be traced to a
named threshold. Thresholds follow common cardiac rehab red-flag guidance and
are tuned per patient where a baseline is recorded.

Adding a rule means adding one function to RULES -- nothing else changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from app.models.clinical import SymptomReport, VitalsRecord
from app.models.enums import FlagSource, Severity
from app.models.program import ExerciseSession
from app.models.user import PatientProfile

# Symptom keywords that warrant review regardless of the patient's own rating.
RED_FLAG_TERMS: tuple[str, ...] = (
    "chest pain", "chest tightness", "chest pressure",
    "shortness of breath", "breathless", "can't breathe", "cannot breathe",
    "fainting", "fainted", "faint", "syncope", "blackout", "passed out",
    "palpitations", "irregular heartbeat",
    "swelling", "swollen ankles", "oedema", "edema",
    "dizzy", "dizziness", "lightheaded",
)


@dataclass(frozen=True)
class RuleResult:
    rule_code: str
    severity: Severity
    message: str


# --------------------------------------------------------------------------
# Vitals rules
# --------------------------------------------------------------------------

def _rule_hypertensive_crisis(v: VitalsRecord, p: PatientProfile) -> Optional[RuleResult]:
    if v.systolic is None and v.diastolic is None:
        return None
    if (v.systolic or 0) >= 180 or (v.diastolic or 0) >= 120:
        return RuleResult(
            "BP_HYPERTENSIVE_CRISIS",
            Severity.SEVERE,
            f"Blood pressure {v.systolic}/{v.diastolic} mmHg is in the hypertensive "
            "crisis range (>=180/120). Urgent clinical review advised.",
        )
    return None


def _rule_hypertension(v: VitalsRecord, p: PatientProfile) -> Optional[RuleResult]:
    if (v.systolic or 0) >= 160 or (v.diastolic or 0) >= 100:
        return RuleResult(
            "BP_HIGH",
            Severity.MODERATE,
            f"Blood pressure {v.systolic}/{v.diastolic} mmHg is above the "
            "programme target (<160/100).",
        )
    return None


def _rule_hypotension(v: VitalsRecord, p: PatientProfile) -> Optional[RuleResult]:
    if v.systolic is not None and v.systolic <= 90:
        return RuleResult(
            "BP_LOW",
            Severity.MODERATE,
            f"Systolic blood pressure {v.systolic} mmHg is low (<=90) and may cause "
            "dizziness during exercise.",
        )
    return None


def _rule_tachycardia(v: VitalsRecord, p: PatientProfile) -> Optional[RuleResult]:
    if v.heart_rate is None:
        return None
    # Prefer the patient's prescribed ceiling; fall back to a general threshold.
    ceiling = p.target_hr_max or 120
    if v.heart_rate > ceiling:
        return RuleResult(
            "HR_ABOVE_TARGET",
            Severity.MODERATE if v.heart_rate <= ceiling + 20 else Severity.SEVERE,
            f"Resting heart rate {v.heart_rate} bpm exceeds this patient's ceiling "
            f"of {ceiling} bpm.",
        )
    return None


def _rule_bradycardia(v: VitalsRecord, p: PatientProfile) -> Optional[RuleResult]:
    if v.heart_rate is not None and v.heart_rate < 45:
        return RuleResult(
            "HR_LOW",
            Severity.MODERATE,
            f"Heart rate {v.heart_rate} bpm is below 45 bpm.",
        )
    return None


def _rule_hypoxaemia(v: VitalsRecord, p: PatientProfile) -> Optional[RuleResult]:
    if v.spo2 is None:
        return None
    if v.spo2 < 90:
        return RuleResult(
            "SPO2_LOW", Severity.SEVERE,
            f"Oxygen saturation {v.spo2}% is below 90%.",
        )
    if v.spo2 < 94:
        return RuleResult(
            "SPO2_BORDERLINE", Severity.MILD,
            f"Oxygen saturation {v.spo2}% is below the 94% comfort threshold.",
        )
    return None


VITALS_RULES: Sequence[Callable[[VitalsRecord, PatientProfile], Optional[RuleResult]]] = (
    _rule_hypertensive_crisis,
    _rule_hypertension,
    _rule_hypotension,
    _rule_tachycardia,
    _rule_bradycardia,
    _rule_hypoxaemia,
)


def evaluate_vitals(record: VitalsRecord, profile: PatientProfile) -> List[RuleResult]:
    """Return every rule triggered by a vitals reading.

    Crisis-level blood pressure suppresses the plain high-BP rule so the queue
    shows one clear flag rather than two describing the same reading.
    """
    results = [r for rule in VITALS_RULES if (r := rule(record, profile)) is not None]
    codes = {r.rule_code for r in results}
    if "BP_HYPERTENSIVE_CRISIS" in codes:
        results = [r for r in results if r.rule_code != "BP_HIGH"]
    if "SPO2_LOW" in codes:
        results = [r for r in results if r.rule_code != "SPO2_BORDERLINE"]
    return results


# --------------------------------------------------------------------------
# Symptom rules
# --------------------------------------------------------------------------

def evaluate_symptom(report: SymptomReport, profile: PatientProfile) -> List[RuleResult]:
    results: List[RuleResult] = []
    text = report.description.lower()

    matched = [term for term in RED_FLAG_TERMS if term in text]
    if matched:
        results.append(
            RuleResult(
                "SYMPTOM_RED_FLAG",
                Severity.SEVERE if report.severity is Severity.SEVERE else Severity.MODERATE,
                "Patient reported a cardiac red-flag symptom "
                f"({', '.join(sorted(set(matched))[:3])}).",
            )
        )
    elif report.severity is Severity.SEVERE:
        results.append(
            RuleResult(
                "SYMPTOM_SEVERE",
                Severity.MODERATE,
                "Patient rated a symptom as severe.",
            )
        )
    return results


# --------------------------------------------------------------------------
# Exercise session rules
# --------------------------------------------------------------------------

def evaluate_session(session: ExerciseSession, profile: PatientProfile) -> List[RuleResult]:
    results: List[RuleResult] = []
    if session.perceived_exertion is not None and session.perceived_exertion >= 17:
        results.append(
            RuleResult(
                "EXERTION_HIGH",
                Severity.MODERATE,
                f"Perceived exertion {session.perceived_exertion}/20 is above the "
                "recommended range for supervised rehab (target 11-14).",
            )
        )
    if not session.completed:
        results.append(
            RuleResult(
                "SESSION_ABANDONED",
                Severity.MILD,
                "Patient did not complete a prescribed exercise session.",
            )
        )
    return results


SOURCE_EVALUATORS = {
    FlagSource.VITALS: evaluate_vitals,
    FlagSource.SYMPTOM: evaluate_symptom,
    FlagSource.SESSION: evaluate_session,
}

"""Six-minute walk test: screening, prediction and interpretation.

Sources for the numbers used here:
  - 6MWT protocol, contraindications and stopping criteria: StatPearls,
    https://www.ncbi.nlm.nih.gov/books/NBK576420/
  - Predicted distance: Enright PL, Sherrill DL. Reference equations for the
    six-minute walk in healthy adults. Am J Respir Crit Care Med 1998.

Every threshold below is written as a named constant with its source, because a
magic number in a clinical calculation is unreviewable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from app.models.assessment import WalkTest
from app.models.enums import SexAtBirth, Severity, WalkTestStatus
from app.models.user import PatientProfile
from app.services.risk_rules import RuleResult

# --- screening thresholds --------------------------------------------------
RESTING_HR_CEILING = 120          # relative contraindication
SEVERE_SYSTOLIC = 180             # relative: severe uncontrolled hypertension
SEVERE_DIASTOLIC = 110
ACS_EXCLUSION_DAYS = 30           # absolute: ACS within 30 days

# --- during-test thresholds ------------------------------------------------
CRITICAL_DESATURATION = 80        # commonest reason a test is terminated
CONCERNING_DESATURATION = 88      # widely used threshold for clinical concern

# --- interpretation --------------------------------------------------------
MCID_METRES = 30.0                # minimal clinically important difference
LLN_OFFSET_FEMALE = 139.0         # lower limit of normal, Enright & Sherrill
LLN_OFFSET_MALE = 153.0

# --- prefill ---------------------------------------------------------------
# A reading older than this is still shown, but marked for retaking rather than
# confirmation. Ninety minutes is generous for a clinic visit and short enough
# that a resting heart rate carried over from yesterday can never be accepted
# with a single tap.
VITALS_STALE_AFTER = timedelta(minutes=90)


@dataclass
class ScreeningResult:
    """Whether the test may proceed, and why not if it may not."""

    cleared: bool
    absolute_blocks: List[str] = field(default_factory=list)
    relative_cautions: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.absolute_blocks:
            return "Test must not proceed: " + "; ".join(self.absolute_blocks)
        if self.relative_cautions:
            return "Proceed only with clinician supervision: " + "; ".join(self.relative_cautions)
        return "No contraindications identified."


def screen(
    *,
    resting_heart_rate: Optional[int] = None,
    systolic: Optional[int] = None,
    diastolic: Optional[int] = None,
    acs_within_30_days: bool = False,
    syncope_history: bool = False,
    acute_respiratory_failure: bool = False,
    unstable_angina: bool = False,
) -> ScreeningResult:
    """Contraindication check, run before a test is allowed to start.

    Absolute findings block the test outright. Relative findings do not block
    it but require supervision -- the distinction is the protocol's, and
    collapsing the two would either forbid safe tests or permit unsafe ones.
    """
    absolute: List[str] = []
    relative: List[str] = []

    if acs_within_30_days or unstable_angina:
        absolute.append("acute coronary syndrome or unstable angina within the last 30 days")
    if acute_respiratory_failure:
        absolute.append("acute respiratory failure")
    if syncope_history:
        absolute.append("history of syncope")

    if resting_heart_rate is not None and resting_heart_rate > RESTING_HR_CEILING:
        relative.append(f"resting heart rate {resting_heart_rate} bpm is above {RESTING_HR_CEILING}")
    if (systolic is not None and systolic >= SEVERE_SYSTOLIC) or (
        diastolic is not None and diastolic >= SEVERE_DIASTOLIC
    ):
        relative.append(
            f"blood pressure {systolic or '–'}/{diastolic or '–'} mmHg indicates severe "
            "uncontrolled hypertension"
        )

    return ScreeningResult(cleared=not absolute, absolute_blocks=absolute, relative_cautions=relative)


def age_from(date_of_birth: Optional[date]) -> Optional[int]:
    if date_of_birth is None:
        return None
    today = datetime.now(timezone.utc).date()
    return today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )


def predicted_distance(
    *, age: Optional[int], height_cm: Optional[float], weight_kg: Optional[float],
    sex: Optional[SexAtBirth],
) -> Optional[float]:
    """Enright & Sherrill predicted 6MWD in metres, or None if inputs are missing.

    Returning None rather than guessing matters: a percentage of a predicted
    distance computed from an assumed height is a number that looks clinical and
    means nothing.
    """
    if age is None or height_cm is None or weight_kg is None or sex is None:
        return None
    if sex is SexAtBirth.MALE:
        distance = (7.57 * height_cm) - (5.02 * age) - (1.76 * weight_kg) - 309.0
    elif sex is SexAtBirth.FEMALE:
        distance = (2.11 * height_cm) - (2.29 * weight_kg) - (5.78 * age) + 667.0
    else:
        return None
    return round(max(distance, 0.0), 1)


def lower_limit_of_normal(predicted: Optional[float], sex: Optional[SexAtBirth]) -> Optional[float]:
    if predicted is None or sex is None or sex is SexAtBirth.UNSPECIFIED:
        return None
    offset = LLN_OFFSET_MALE if sex is SexAtBirth.MALE else LLN_OFFSET_FEMALE
    return round(max(predicted - offset, 0.0), 1)


def interpret(
    test: WalkTest, profile: PatientProfile, weight_kg: Optional[float],
) -> tuple[Optional[float], Optional[float], Optional[bool]]:
    """Return (predicted distance, percent predicted, below lower limit)."""
    predicted = predicted_distance(
        age=age_from(profile.date_of_birth),
        height_cm=profile.height_cm,
        weight_kg=weight_kg,
        sex=profile.sex_at_birth,
    )
    if predicted is None or predicted == 0:
        return None, None, None

    percent = round(test.distance_m / predicted * 100.0, 1)
    lln = lower_limit_of_normal(predicted, profile.sex_at_birth)
    below = test.distance_m < lln if lln is not None else None
    return predicted, percent, below


def evaluate(test: WalkTest, previous: Optional[WalkTest] = None) -> List[RuleResult]:
    """Flags raised by a completed test."""
    results: List[RuleResult] = []

    if test.lowest_spo2 is not None:
        if test.lowest_spo2 < CRITICAL_DESATURATION:
            results.append(RuleResult(
                "WALK_DESATURATION_SEVERE", Severity.SEVERE,
                f"Oxygen saturation fell to {test.lowest_spo2}% during the six-minute walk "
                f"(below {CRITICAL_DESATURATION}%), the usual threshold for stopping a test.",
            ))
        elif test.lowest_spo2 < CONCERNING_DESATURATION:
            results.append(RuleResult(
                "WALK_DESATURATION", Severity.MODERATE,
                f"Oxygen saturation fell to {test.lowest_spo2}% during the six-minute walk.",
            ))

    if test.status is WalkTestStatus.STOPPED_EARLY:
        results.append(RuleResult(
            "WALK_STOPPED_EARLY", Severity.MODERATE,
            f"Six-minute walk test stopped early: {test.stop_reason or 'reason not recorded'}.",
        ))

    if test.below_lower_limit:
        results.append(RuleResult(
            "WALK_BELOW_NORMAL", Severity.MILD,
            f"Distance {test.distance_m:.0f} m is below the lower limit of normal for this "
            f"patient (predicted {test.predicted_distance_m:.0f} m).",
        ))

    # A drop beyond the MCID is meaningful; smaller changes are measurement noise
    # and flagging them would train the team to ignore the flag.
    if previous is not None:
        change = test.distance_m - previous.distance_m
        if change <= -MCID_METRES:
            results.append(RuleResult(
                "WALK_DISTANCE_DECLINE", Severity.MODERATE,
                f"Walking distance fell by {abs(change):.0f} m since the previous test "
                f"({previous.distance_m:.0f} m to {test.distance_m:.0f} m), beyond the "
                f"{MCID_METRES:.0f} m considered clinically meaningful.",
            ))

    return results


def change_since(test: WalkTest, previous: Optional[WalkTest]) -> Optional[dict]:
    """Change versus the previous test, with the MCID applied."""
    if previous is None:
        return None
    delta = round(test.distance_m - previous.distance_m, 1)
    return {
        "previous_distance_m": previous.distance_m,
        "previous_performed_at": previous.performed_at,
        "change_m": delta,
        "clinically_meaningful": abs(delta) >= MCID_METRES,
        "direction": "improved" if delta > 0 else "declined" if delta < 0 else "unchanged",
    }


def vitals_are_stale(recorded_at: datetime, *, now: Optional[datetime] = None) -> bool:
    """Whether a stored reading is too old to be confirmed rather than retaken."""
    now = now or datetime.now(timezone.utc)
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    return (now - recorded_at) > VITALS_STALE_AFTER


def prediction_inputs_missing(
    profile: PatientProfile, weight_kg: Optional[float]
) -> List[str]:
    """Which inputs the predicted-distance equation still lacks.

    Named in the words a person would use, because this list is shown to them:
    the point is to say what to go and fill in, not to name a column.
    """
    missing: List[str] = []
    if age_from(profile.date_of_birth) is None:
        missing.append("date of birth")
    if profile.height_cm is None:
        missing.append("height")
    if profile.sex_at_birth is None or profile.sex_at_birth is SexAtBirth.UNSPECIFIED:
        missing.append("sex at birth")
    if weight_kg is None:
        missing.append("weight")
    return missing

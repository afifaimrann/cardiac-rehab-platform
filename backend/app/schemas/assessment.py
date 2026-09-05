"""Six-minute walk test payloads."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import SexAtBirth, WalkTestStatus
from app.schemas.clinical import RiskFlagRead


class ScreeningRequest(BaseModel):
    """Answers to the pre-test contraindication questions."""

    resting_heart_rate: Optional[int] = Field(default=None, ge=20, le=250)
    systolic: Optional[int] = Field(default=None, ge=50, le=300)
    diastolic: Optional[int] = Field(default=None, ge=30, le=200)
    acs_within_30_days: bool = False
    unstable_angina: bool = False
    syncope_history: bool = False
    acute_respiratory_failure: bool = False


class ScreeningResponse(BaseModel):
    cleared: bool = Field(description="False when an absolute contraindication is present.")
    absolute_blocks: List[str] = []
    relative_cautions: List[str] = []
    summary: str


class WalkTestCreate(BaseModel):
    performed_at: Optional[datetime] = None
    course_length_m: float = Field(default=30.0, ge=5, le=100)
    laps: Optional[int] = Field(default=None, ge=0, le=200)
    partial_lap_m: Optional[float] = Field(default=None, ge=0)
    distance_m: Optional[float] = Field(
        default=None, ge=0, le=1200,
        description="Total metres walked. Computed from laps if omitted.",
    )

    pre_heart_rate: Optional[int] = Field(default=None, ge=20, le=250)
    pre_spo2: Optional[int] = Field(default=None, ge=50, le=100)
    pre_systolic: Optional[int] = Field(default=None, ge=50, le=300)
    pre_diastolic: Optional[int] = Field(default=None, ge=30, le=200)
    pre_borg_dyspnoea: Optional[float] = Field(default=None, ge=0, le=10)
    pre_borg_fatigue: Optional[float] = Field(default=None, ge=0, le=10)

    lowest_spo2: Optional[int] = Field(default=None, ge=50, le=100)
    rest_count: int = Field(default=0, ge=0, le=20)
    rest_seconds: int = Field(default=0, ge=0, le=360)

    post_heart_rate: Optional[int] = Field(default=None, ge=20, le=250)
    post_spo2: Optional[int] = Field(default=None, ge=50, le=100)
    post_systolic: Optional[int] = Field(default=None, ge=50, le=300)
    post_diastolic: Optional[int] = Field(default=None, ge=30, le=200)
    post_borg_dyspnoea: Optional[float] = Field(default=None, ge=0, le=10)
    post_borg_fatigue: Optional[float] = Field(default=None, ge=0, le=10)

    status: WalkTestStatus = WalkTestStatus.COMPLETED
    stop_reason: Optional[str] = Field(default=None, max_length=200)
    symptoms: Optional[str] = Field(default=None, max_length=2000)
    used_oxygen: bool = False
    notes: Optional[str] = Field(default=None, max_length=2000)
    # Weight on the day; the predicted-distance equation needs it and body
    # weight moves enough over a programme to matter.
    weight_kg: Optional[float] = Field(default=None, gt=0, le=400)

    # The screening answers as given on the day. Recorded with the test so a
    # later reviewer can see what was asked, and so the next test can offer
    # them back for confirmation.
    screen_acs_within_30_days: Optional[bool] = None
    screen_unstable_angina: Optional[bool] = None
    screen_syncope_history: Optional[bool] = None
    screen_acute_respiratory_failure: Optional[bool] = None

    @model_validator(mode="after")
    def _resolve_distance(self) -> "WalkTestCreate":
        if self.distance_m is None:
            if self.laps is None:
                raise ValueError("Provide either distance_m, or laps to compute it from.")
            self.distance_m = self.laps * self.course_length_m + (self.partial_lap_m or 0.0)
        if self.status is WalkTestStatus.STOPPED_EARLY and not self.stop_reason:
            raise ValueError("stop_reason is required when a test was stopped early.")
        return self


class WalkTestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    performed_at: datetime
    course_length_m: float
    laps: Optional[int] = None
    distance_m: float

    pre_heart_rate: Optional[int] = None
    pre_spo2: Optional[int] = None
    pre_borg_dyspnoea: Optional[float] = None
    pre_borg_fatigue: Optional[float] = None

    lowest_spo2: Optional[int] = None
    rest_count: int
    rest_seconds: int

    post_heart_rate: Optional[int] = None
    post_spo2: Optional[int] = None
    post_borg_dyspnoea: Optional[float] = None
    post_borg_fatigue: Optional[float] = None

    status: WalkTestStatus
    stop_reason: Optional[str] = None
    symptoms: Optional[str] = None
    used_oxygen: bool
    notes: Optional[str] = None

    predicted_distance_m: Optional[float] = None
    percent_predicted: Optional[float] = None
    below_lower_limit: Optional[bool] = None


class WalkTestChange(BaseModel):
    previous_distance_m: float
    previous_performed_at: datetime
    change_m: float
    clinically_meaningful: bool = Field(
        description="True when the change is at least the 30 m MCID."
    )
    direction: str


class WalkTestCreateResponse(BaseModel):
    walk_test: WalkTestRead
    change: Optional[WalkTestChange] = None
    flags_raised: List[RiskFlagRead] = []


class PrefillVitals(BaseModel):
    """The patient's most recent readings, offered as starting values."""

    recorded_at: datetime
    heart_rate: Optional[int] = None
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    spo2: Optional[int] = None
    # Null when the newest record carried no weight. `weight_kg` on the parent
    # is the value actually used, found from whichever record last had one.
    weight_kg: Optional[float] = None
    stale: bool = Field(
        description="True when the reading is old enough that it should be retaken, "
        "not merely confirmed.",
    )


class PrefillScreening(BaseModel):
    """The previous test's contraindication answers."""

    answered_at: datetime
    acs_within_30_days: bool
    unstable_angina: bool
    syncope_history: bool
    acute_respiratory_failure: bool


class WalkTestPrefill(BaseModel):
    """What the record already knows, so a test only asks for what is new.

    Nothing here is a measurement in its own right -- every value is a previous
    reading offered for confirmation, with the time it was taken, so that the
    person running the test can see what they are agreeing to.
    """

    vitals: Optional[PrefillVitals] = None
    weight_kg: Optional[float] = None
    weight_recorded_at: Optional[datetime] = None
    height_cm: Optional[float] = None
    sex_at_birth: Optional[SexAtBirth] = None
    age: Optional[int] = None
    course_length_m: float = 30.0
    missing_for_prediction: List[str] = Field(
        default=[],
        description="Profile fields still needed before a percent-predicted can be computed.",
    )
    previous_screening: Optional[PrefillScreening] = None
    previous_distance_m: Optional[float] = None
    previous_performed_at: Optional[datetime] = None

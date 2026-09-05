"""Six-minute walk test: screening, prediction and interpretation.

The clinical constants are asserted directly against their sources, so a change
to a threshold has to be a deliberate edit to a test rather than a silent drift.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.assessment import WalkTest
from app.models.enums import SexAtBirth, Severity, WalkTestStatus
from app.models.user import PatientProfile
from app.services import walk_test as service


def profile(**kwargs) -> PatientProfile:
    return PatientProfile(user_id="u1", **kwargs)


def walk(**kwargs) -> WalkTest:
    """Factory, not a test — pytest collects anything named test*."""
    kwargs.setdefault("distance_m", 400.0)
    return WalkTest(patient_id="p1", **kwargs)


# --------------------------------------------------------------------------
# Screening
# --------------------------------------------------------------------------

def test_no_findings_clears_the_test():
    result = service.screen(resting_heart_rate=72, systolic=124, diastolic=78)
    assert result.cleared
    assert result.absolute_blocks == [] and result.relative_cautions == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"acs_within_30_days": True},
        {"unstable_angina": True},
        {"syncope_history": True},
        {"acute_respiratory_failure": True},
    ],
)
def test_absolute_contraindications_block_the_test(kwargs):
    result = service.screen(**kwargs)
    assert result.cleared is False
    assert result.absolute_blocks


def test_high_resting_heart_rate_is_a_caution_not_a_block():
    """The protocol separates absolute from relative findings; collapsing them
    would either forbid safe tests or permit unsafe ones."""
    result = service.screen(resting_heart_rate=130)
    assert result.cleared is True
    assert any("resting heart rate" in c for c in result.relative_cautions)


def test_severe_hypertension_is_a_caution():
    result = service.screen(systolic=190, diastolic=115)
    assert result.cleared is True
    assert any("hypertension" in c for c in result.relative_cautions)


def test_resting_heart_rate_at_the_ceiling_is_allowed():
    """120 is the ceiling; the caution applies above it, not at it."""
    assert service.screen(resting_heart_rate=120).relative_cautions == []
    assert service.screen(resting_heart_rate=121).relative_cautions != []


# --------------------------------------------------------------------------
# Predicted distance
# --------------------------------------------------------------------------

def test_predicted_distance_matches_the_published_equation():
    """Enright & Sherrill: men 7.57·height − 5.02·age − 1.76·weight − 309."""
    expected = (7.57 * 175) - (5.02 * 60) - (1.76 * 80) - 309
    got = service.predicted_distance(age=60, height_cm=175, weight_kg=80, sex=SexAtBirth.MALE)
    assert got == pytest.approx(expected, abs=0.1)


def test_predicted_distance_female_equation():
    """Women: 2.11·height − 2.29·weight − 5.78·age + 667."""
    expected = (2.11 * 160) - (2.29 * 65) - (5.78 * 62) + 667
    got = service.predicted_distance(age=62, height_cm=160, weight_kg=65, sex=SexAtBirth.FEMALE)
    assert got == pytest.approx(expected, abs=0.1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"age": None, "height_cm": 170, "weight_kg": 70, "sex": SexAtBirth.MALE},
        {"age": 60, "height_cm": None, "weight_kg": 70, "sex": SexAtBirth.MALE},
        {"age": 60, "height_cm": 170, "weight_kg": None, "sex": SexAtBirth.MALE},
        {"age": 60, "height_cm": 170, "weight_kg": 70, "sex": None},
        {"age": 60, "height_cm": 170, "weight_kg": 70, "sex": SexAtBirth.UNSPECIFIED},
    ],
)
def test_missing_inputs_return_none_rather_than_a_guess(kwargs):
    """A percent-predicted computed from an assumed height looks clinical and
    means nothing."""
    assert service.predicted_distance(**kwargs) is None


def test_lower_limit_of_normal_uses_the_published_offsets():
    assert service.lower_limit_of_normal(500.0, SexAtBirth.MALE) == pytest.approx(500 - 153)
    assert service.lower_limit_of_normal(500.0, SexAtBirth.FEMALE) == pytest.approx(500 - 139)


# --------------------------------------------------------------------------
# Interpretation
# --------------------------------------------------------------------------

def codes(results):
    return {r.rule_code for r in results}


def test_severe_desaturation_is_flagged_as_severe():
    results = service.evaluate(walk(lowest_spo2=78))
    assert codes(results) == {"WALK_DESATURATION_SEVERE"}
    assert results[0].severity is Severity.SEVERE


def test_moderate_desaturation_is_flagged_separately():
    assert codes(service.evaluate(walk(lowest_spo2=85))) == {"WALK_DESATURATION"}


def test_normal_saturation_raises_nothing():
    assert service.evaluate(walk(lowest_spo2=95)) == []


def test_final_saturation_does_not_hide_a_dip():
    """The nadir is recorded separately because desaturation often recovers
    before the six minutes are up."""
    subject = walk(lowest_spo2=79, post_spo2=97)
    assert "WALK_DESATURATION_SEVERE" in codes(service.evaluate(subject))


def test_stopping_early_is_flagged_with_its_reason():
    subject = walk(status=WalkTestStatus.STOPPED_EARLY, stop_reason="chest tightness")
    results = service.evaluate(subject)
    assert "WALK_STOPPED_EARLY" in codes(results)
    assert "chest tightness" in results[0].message


def test_distance_below_the_lower_limit_is_flagged():
    subject = walk(distance_m=280.0, below_lower_limit=True, predicted_distance_m=480.0)
    assert "WALK_BELOW_NORMAL" in codes(service.evaluate(subject))


def test_decline_beyond_the_mcid_is_flagged():
    previous = walk(distance_m=420.0)
    current = walk(distance_m=380.0)          # 40 m worse
    assert "WALK_DISTANCE_DECLINE" in codes(service.evaluate(current, previous))


def test_decline_within_the_mcid_is_not_flagged():
    """Smaller changes are measurement noise; flagging them would train the team
    to ignore the flag."""
    previous = walk(distance_m=420.0)
    current = walk(distance_m=400.0)          # 20 m, below the 30 m MCID
    assert "WALK_DISTANCE_DECLINE" not in codes(service.evaluate(current, previous))


def test_improvement_is_never_flagged():
    previous = walk(distance_m=350.0)
    current = walk(distance_m=450.0)
    assert service.evaluate(current, previous) == []


def test_change_reports_direction_and_significance():
    previous = walk(distance_m=350.0, performed_at=datetime.now(timezone.utc) - timedelta(days=28))
    change = service.change_since(walk(distance_m=395.0), previous)
    assert change["change_m"] == pytest.approx(45.0)
    assert change["direction"] == "improved"
    assert change["clinically_meaningful"] is True


def test_change_is_none_for_a_first_test():
    assert service.change_since(walk(), None) is None


# ===========================================================================
# Prefill: what the record already knows, so the test stops asking for it
# ===========================================================================
class TestVitalsFreshness:
    """A carried-over reading must be confirmable only while it is current."""

    def test_a_reading_taken_now_is_fresh(self):
        from datetime import datetime, timezone
        assert not service.vitals_are_stale(datetime.now(timezone.utc))

    def test_yesterdays_reading_is_stale(self):
        from datetime import datetime, timedelta, timezone
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert service.vitals_are_stale(yesterday)

    def test_a_naive_timestamp_is_read_as_utc_not_local(self):
        """SQLite hands back naive datetimes; treating them as local time would
        mark a fresh reading stale by the size of the offset."""
        from datetime import datetime, timezone
        naive = datetime.now(timezone.utc).replace(tzinfo=None)
        assert not service.vitals_are_stale(naive)


class TestPredictionInputs:
    def test_names_every_missing_input(self):
        from app.models.user import PatientProfile
        missing = service.prediction_inputs_missing(PatientProfile(), None)
        assert set(missing) == {"date of birth", "height", "sex at birth", "weight"}

    def test_unspecified_sex_counts_as_missing(self):
        """The equations are sex-specific; 'unspecified' cannot produce a number."""
        from app.models.enums import SexAtBirth
        from app.models.user import PatientProfile

        profile = PatientProfile(
            date_of_birth=date(1970, 1, 1), height_cm=165,
            sex_at_birth=SexAtBirth.UNSPECIFIED,
        )
        assert service.prediction_inputs_missing(profile, 70.0) == ["sex at birth"]

    def test_a_complete_profile_is_missing_nothing(self):
        from app.models.enums import SexAtBirth
        from app.models.user import PatientProfile

        profile = PatientProfile(
            date_of_birth=date(1970, 1, 1), height_cm=165, sex_at_birth=SexAtBirth.FEMALE
        )
        assert service.prediction_inputs_missing(profile, 70.0) == []


class TestPrefillEndpoint:
    async def test_a_new_patient_gets_empty_prefill_not_an_error(self, client, patient):
        r = await client.get("/api/v1/walk-tests/prefill", headers=patient["headers"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["vitals"] is None
        assert body["previous_screening"] is None
        assert set(body["missing_for_prediction"]) == {
            "date of birth", "height", "sex at birth", "weight"
        }

    async def test_the_latest_reading_is_offered_with_its_timestamp(
        self, client, patient
    ):
        await client.post(
            "/api/v1/vitals",
            json={"systolic": 126, "diastolic": 80, "heart_rate": 71,
                  "spo2": 97, "weight_kg": 68.4},
            headers=patient["headers"],
        )
        body = (await client.get("/api/v1/walk-tests/prefill",
                                 headers=patient["headers"])).json()

        assert body["vitals"]["heart_rate"] == 71
        assert body["vitals"]["systolic"] == 126
        assert body["vitals"]["spo2"] == 97
        # Offered for confirmation, not silently inherited: the caller is told
        # when it was taken and whether that is recent enough.
        assert body["vitals"]["recorded_at"]
        assert body["vitals"]["stale"] is False
        assert body["weight_kg"] == 68.4

    async def test_weight_is_found_in_an_older_record_than_the_newest(
        self, client, patient
    ):
        """Weight is logged less often than blood pressure, so the newest row
        usually has none. Falling back to the newest row alone would ask the
        patient to weigh themselves at every test."""
        await client.post("/api/v1/vitals", json={"weight_kg": 71.2},
                          headers=patient["headers"])
        await client.post("/api/v1/vitals", json={"systolic": 120, "diastolic": 78},
                          headers=patient["headers"])

        body = (await client.get("/api/v1/walk-tests/prefill",
                                 headers=patient["headers"])).json()
        assert body["vitals"]["weight_kg"] is None   # newest row
        assert body["weight_kg"] == 71.2             # found anyway
        assert "weight" not in body["missing_for_prediction"]

    async def test_profile_details_close_the_prediction_gap(self, client, patient):
        await client.patch(
            "/api/v1/me/profile",
            json={"height_cm": 158, "sex_at_birth": "female",
                  "date_of_birth": "1962-03-04"},
            headers=patient["headers"],
        )
        await client.post("/api/v1/vitals", json={"weight_kg": 64.0},
                          headers=patient["headers"])

        body = (await client.get("/api/v1/walk-tests/prefill",
                                 headers=patient["headers"])).json()
        assert body["missing_for_prediction"] == []
        assert body["height_cm"] == 158
        assert body["age"] and body["age"] > 50

    async def test_screening_answers_come_back_from_the_last_test(
        self, client, patient
    ):
        await client.post(
            "/api/v1/walk-tests",
            json={"laps": 12, "partial_lap_m": 10, "pre_heart_rate": 70,
                  "screen_acs_within_30_days": False, "screen_unstable_angina": False,
                  "screen_syncope_history": True,
                  "screen_acute_respiratory_failure": False},
            headers=patient["headers"],
        )
        body = (await client.get("/api/v1/walk-tests/prefill",
                                 headers=patient["headers"])).json()

        prior = body["previous_screening"]
        assert prior is not None
        assert prior["syncope_history"] is True
        assert prior["acs_within_30_days"] is False
        assert prior["answered_at"]
        assert body["previous_distance_m"] == 370

    async def test_a_test_recorded_without_screening_offers_nothing_back(
        self, client, patient
    ):
        """An older record has no stored answers; inventing 'all false' from
        their absence would clear a patient nobody screened."""
        await client.post("/api/v1/walk-tests", json={"laps": 10},
                          headers=patient["headers"])
        body = (await client.get("/api/v1/walk-tests/prefill",
                                 headers=patient["headers"])).json()
        assert body["previous_screening"] is None
        assert body["previous_distance_m"] == 300

    async def test_screening_answers_are_stored_on_the_test(self, client, patient):
        r = await client.post(
            "/api/v1/walk-tests",
            json={"laps": 11, "screen_syncope_history": False,
                  "screen_acs_within_30_days": False, "screen_unstable_angina": False,
                  "screen_acute_respiratory_failure": False},
            headers=patient["headers"],
        )
        assert r.status_code == 201, r.text

    async def test_a_clinician_prefills_from_an_assigned_patients_record(
        self, client, clinician, assigned_patient
    ):
        await client.post("/api/v1/vitals", json={"heart_rate": 66},
                          headers=assigned_patient["headers"])
        r = await client.get(
            f"/api/v1/walk-tests/patients/{assigned_patient['profile_id']}/prefill",
            headers=clinician["headers"],
        )
        assert r.status_code == 200
        assert r.json()["vitals"]["heart_rate"] == 66

    async def test_an_unassigned_clinician_cannot_prefill(
        self, client, session_factory, clinician, assigned_patient
    ):
        from app.models import UserRole
        from tests.conftest import _make_user, auth_headers

        await _make_user(session_factory, "doc2@test.com", UserRole.CLINICIAN, "Dr Two")
        other = await auth_headers(client, "doc2@test.com")
        r = await client.get(
            f"/api/v1/walk-tests/patients/{assigned_patient['profile_id']}/prefill",
            headers=other,
        )
        assert r.status_code == 404

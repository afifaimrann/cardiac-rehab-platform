"""Unit tests for the risk engine.

These run against the rule functions directly -- no database, no HTTP -- so a
threshold change fails here with a clear message rather than somewhere in an
integration test.
"""
import pytest

from app.models.clinical import SymptomReport, VitalsRecord
from app.models.enums import Severity
from app.models.program import ExerciseSession
from app.models.user import PatientProfile
from app.services.risk_rules import evaluate_session, evaluate_symptom, evaluate_vitals


def profile(**kwargs) -> PatientProfile:
    return PatientProfile(user_id="u1", **kwargs)


def vitals(**kwargs) -> VitalsRecord:
    return VitalsRecord(patient_id="p1", **kwargs)


def codes(results) -> set:
    return {r.rule_code for r in results}


@pytest.mark.parametrize(
    "reading,expected",
    [
        ({"systolic": 120, "diastolic": 78, "heart_rate": 70, "spo2": 98}, set()),
        ({"systolic": 186, "diastolic": 122}, {"BP_HYPERTENSIVE_CRISIS"}),
        ({"systolic": 180, "diastolic": 90}, {"BP_HYPERTENSIVE_CRISIS"}),
        ({"systolic": 165, "diastolic": 95}, {"BP_HIGH"}),
        ({"systolic": 88, "diastolic": 60}, {"BP_LOW"}),
        ({"heart_rate": 40}, {"HR_LOW"}),
        ({"spo2": 88}, {"SPO2_LOW"}),
        ({"spo2": 92}, {"SPO2_BORDERLINE"}),
        ({"spo2": 95}, set()),
    ],
)
def test_vitals_thresholds(reading, expected):
    assert codes(evaluate_vitals(vitals(**reading), profile())) == expected


def test_crisis_suppresses_the_redundant_high_bp_flag():
    """One reading should produce one flag, not two describing the same thing."""
    results = evaluate_vitals(vitals(systolic=190, diastolic=125), profile())
    assert codes(results) == {"BP_HYPERTENSIVE_CRISIS"}


def test_low_spo2_suppresses_borderline():
    results = evaluate_vitals(vitals(spo2=85), profile())
    assert codes(results) == {"SPO2_LOW"}


def test_heart_rate_ceiling_is_personalised():
    """A patient with a prescribed ceiling is judged against it, not the default."""
    reading = vitals(heart_rate=115)
    assert codes(evaluate_vitals(reading, profile())) == set()          # default ceiling 120
    assert codes(evaluate_vitals(reading, profile(target_hr_max=110))) == {"HR_ABOVE_TARGET"}


def test_far_above_ceiling_escalates_severity():
    p = profile(target_hr_max=110)
    mild = evaluate_vitals(vitals(heart_rate=120), p)[0]
    bad = evaluate_vitals(vitals(heart_rate=145), p)[0]
    assert mild.severity is Severity.MODERATE
    assert bad.severity is Severity.SEVERE


def test_reading_with_no_measurements_raises_nothing():
    assert evaluate_vitals(vitals(note="felt fine"), profile()) == []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Chest pain when walking", {"SYMPTOM_RED_FLAG"}),
        ("CHEST TIGHTNESS at night", {"SYMPTOM_RED_FLAG"}),
        ("Felt dizzy standing up", {"SYMPTOM_RED_FLAG"}),
        ("Swollen ankles this evening", {"SYMPTOM_RED_FLAG"}),
        ("Slept badly", set()),
    ],
)
def test_symptom_keywords(text, expected):
    report = SymptomReport(patient_id="p1", description=text, severity=Severity.MILD)
    assert codes(evaluate_symptom(report, profile())) == expected


def test_severe_self_rating_flags_even_without_keywords():
    report = SymptomReport(patient_id="p1", description="Just feel awful", severity=Severity.SEVERE)
    assert codes(evaluate_symptom(report, profile())) == {"SYMPTOM_SEVERE"}


def test_red_flag_takes_precedence_over_severity_rule():
    report = SymptomReport(patient_id="p1", description="Chest pain", severity=Severity.SEVERE)
    results = evaluate_symptom(report, profile())
    assert codes(results) == {"SYMPTOM_RED_FLAG"}
    assert results[0].severity is Severity.SEVERE


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"perceived_exertion": 13, "completed": True}, set()),
        ({"perceived_exertion": 18, "completed": True}, {"EXERTION_HIGH"}),
        ({"perceived_exertion": 12, "completed": False}, {"SESSION_ABANDONED"}),
        ({"perceived_exertion": 19, "completed": False}, {"EXERTION_HIGH", "SESSION_ABANDONED"}),
    ],
)
def test_session_rules(kwargs, expected):
    session = ExerciseSession(patient_id="p1", activity="Walk", duration_minutes=30, **kwargs)
    assert codes(evaluate_session(session, profile())) == expected

"""Seed a demo dataset: one admin, one clinician, three patients with history.

Run with:  python -m scripts.seed_demo
Idempotent: existing accounts are reused rather than duplicated.
"""
from __future__ import annotations

import asyncio
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Appointment, AvailabilityRule, DirectMessage, ExercisePlan, ExerciseSession,
    PatientProfile, Severity, SymptomReport, User, UserRole, VitalsRecord,
)
from app.models.enums import (  # noqa: E402
    AppointmentMode, AppointmentStatus, FlagSource,
)
from app.services import scheduling  # noqa: E402
from app.services.meetings import create_room  # noqa: E402
from app.services.flags import persist_flags  # noqa: E402
from app.services.risk_rules import evaluate_session, evaluate_symptom, evaluate_vitals  # noqa: E402

DEMO_PASSWORD = "demo-password-123"

PATIENTS = [
    ("rina@example.com", "Rina Ahmed", "Post-MI rehabilitation, phase II", 62, 118),
    ("kamal@example.com", "Kamal Hossain", "Coronary artery bypass graft, week 6", 70, 125),
    ("nadia@example.com", "Nadia Rahman", "Heart failure with reduced ejection fraction", 74, 110),
]


async def get_or_create_user(db, email: str, name: str, role: UserRole) -> User:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        return existing
    user = User(
        email=email,
        hashed_password=hash_password(DEMO_PASSWORD),
        full_name=name,
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def main() -> None:
    rng = random.Random(42)  # deterministic demo data
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Created for the demo sign-in list; nothing below needs the object.
        await get_or_create_user(db, "admin@example.com", "Admin User", UserRole.ADMIN)
        clinician = await get_or_create_user(
            db, "dr.chowdhury@example.com", "Dr. Chowdhury", UserRole.CLINICIAN
        )

        # A weekly rota, so patients have something to book against. Published
        # once for the clinician rather than per patient.
        rota = list((await db.execute(
            select(AvailabilityRule).where(AvailabilityRule.clinician_id == clinician.id)
        )).scalars().all())
        if not rota:
            for weekday, mode, location in [
                (1, AppointmentMode.ONLINE, None),
                (3, AppointmentMode.ONLINE, None),
                (4, AppointmentMode.IN_PERSON, "Cardiac rehab suite, level 2"),
            ]:
                rule = AvailabilityRule(
                    clinician_id=clinician.id, weekday=weekday,
                    start_time=time(9, 0), end_time=time(13, 0), slot_minutes=30,
                    mode=mode, location=location,
                )
                db.add(rule)
                rota.append(rule)
            await db.flush()

        booked: list[Appointment] = []

        for email, name, condition, resting_hr, hr_max in PATIENTS:
            user = await get_or_create_user(db, email, name, UserRole.PATIENT)
            profile = (
                await db.execute(select(PatientProfile).where(PatientProfile.user_id == user.id))
            ).scalar_one_or_none()
            if profile is None:
                profile = PatientProfile(user_id=user.id)
                db.add(profile)
                await db.flush()

            profile.clinician_id = clinician.id
            profile.primary_condition = condition
            profile.resting_hr_baseline = resting_hr
            profile.target_hr_max = hr_max

            # Skip patients that already have history.
            has_data = (
                await db.execute(
                    select(VitalsRecord.id).where(VitalsRecord.patient_id == profile.id).limit(1)
                )
            ).scalar_one_or_none()
            if has_data:
                continue

            plan = ExercisePlan(
                patient_id=profile.id,
                prescribed_by_id=clinician.id,
                title="Phase II walking and light resistance",
                starts_on=date.today() - timedelta(days=21),
                sessions_per_week=3,
                minutes_per_session=30,
                target_exertion_max=14,
                instructions="Warm up 5 minutes. Stop if you feel chest pain or dizziness.",
            )
            db.add(plan)
            await db.flush()

            # 28 days of vitals, with a couple of deliberately concerning days.
            for day in range(28, 0, -1):
                ts = now - timedelta(days=day, hours=rng.randint(0, 6))
                systolic, diastolic, hr = 120 + rng.randint(-8, 12), 78 + rng.randint(-6, 8), resting_hr + rng.randint(-5, 8)
                if day == 3 and email == PATIENTS[0][0]:
                    systolic, diastolic = 186, 122      # hypertensive crisis
                if day == 9 and email == PATIENTS[1][0]:
                    hr = hr_max + 15                     # above ceiling
                record = VitalsRecord(
                    patient_id=profile.id, recorded_at=ts,
                    systolic=systolic, diastolic=diastolic, heart_rate=hr,
                    spo2=rng.choice([96, 97, 98, 99]),
                    weight_kg=round(68 + rng.random() * 12, 1),
                )
                db.add(record)
                await db.flush()
                await persist_flags(
                    db, profile, FlagSource.VITALS, record.id, evaluate_vitals(record, profile)
                )

            # Sessions, with adherence varying by patient.
            completed_rate = {PATIENTS[0][0]: 0.9, PATIENTS[1][0]: 0.6, PATIENTS[2][0]: 0.3}[email]
            for day in range(27, 0, -2):
                if rng.random() > completed_rate:
                    continue
                session = ExerciseSession(
                    patient_id=profile.id, plan_id=plan.id,
                    performed_at=now - timedelta(days=day),
                    activity=rng.choice(["Treadmill walk", "Stationary cycle", "Resistance band set"]),
                    duration_minutes=rng.choice([20, 25, 30, 35]),
                    perceived_exertion=rng.choice([11, 12, 13, 13, 14, 17]),
                    completed=rng.random() > 0.1,
                )
                db.add(session)
                await db.flush()
                await persist_flags(
                    db, profile, FlagSource.SESSION, session.id, evaluate_session(session, profile)
                )

            for text, sev, days_ago in [
                ("Mild tiredness in the afternoon", Severity.MILD, 12),
                ("Chest tightness while climbing stairs", Severity.MODERATE, 4),
            ]:
                report = SymptomReport(
                    patient_id=profile.id, recorded_at=now - timedelta(days=days_ago),
                    description=text, severity=sev,
                )
                db.add(report)
                await db.flush()
                await persist_flags(
                    db, profile, FlagSource.SYMPTOM, report.id, evaluate_symptom(report, profile)
                )

            # --- one booked consultation, so the module is not empty ------
            if email == PATIENTS[0][0]:
                slots = scheduling.generate_slots(
                    rota, days=7, taken_keys=[a.slot_key for a in booked if a.slot_key]
                )
                if slots:
                    slot = slots[2 if len(slots) > 2 else 0]
                    meeting = create_room()
                    appointment = Appointment(
                        patient_id=profile.id, clinician_id=clinician.id,
                        slot_key=slot.key, starts_at=slot.starts_at, ends_at=slot.ends_at,
                        mode=slot.mode, location=slot.location,
                        reason="More breathless than usual on the stairs",
                        status=AppointmentStatus.SCHEDULED,
                        meeting_provider=meeting.provider, meeting_room=meeting.room,
                        meeting_url=meeting.url,
                    )
                    db.add(appointment)
                    booked.append(appointment)

            # --- a short thread with the care team ------------------------
            if email in (PATIENTS[0][0], PATIENTS[1][0]):
                db.add(DirectMessage(
                    patient_id=profile.id, sender_id=user.id,
                    sent_at=now - timedelta(days=3),
                    body="I managed the full thirty minutes on Tuesday but my ankles "
                         "looked puffy that evening. Is that something to worry about?",
                ))
                db.add(DirectMessage(
                    patient_id=profile.id, sender_id=clinician.id,
                    sent_at=now - timedelta(days=2, hours=4),
                    read_at=now - timedelta(days=2),
                    body="Well done on the thirty minutes. Weigh yourself each morning "
                         "before breakfast this week and log it here — if you gain more "
                         "than two kilos in three days, call us rather than waiting.",
                ))

        await db.commit()

    print("Demo data ready. All accounts use password:", DEMO_PASSWORD)
    print("  Rota published Tue/Thu (video) and Fri (in person), 09:00-13:00.")
    print("  admin@example.com          (admin)")
    print("  dr.chowdhury@example.com   (clinician)")
    for email, name, *_ in PATIENTS:
        print(f"  {email:<26} (patient - {name})")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

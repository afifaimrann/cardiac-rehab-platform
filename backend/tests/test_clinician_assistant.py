"""The clinician's assistant.

Two things are worth testing here and one of them is not the prose. The first is
that the tool layer physically cannot reach another patient's record. The second
is that the feature still answers with no language model configured, which is
the state the whole suite runs in.
"""
import inspect

from app.models import UserRole
from app.services import clinician_assistant
from app.services.clinician_assistant import RecordTools, TOOL_SPECS
from tests.conftest import _make_user, auth_headers


# --- the security property -------------------------------------------------
def test_no_tool_accepts_a_patient_identifier():
    """The model picks the lookup; it never picks the patient.

    If a tool ever grows a patient_id parameter, a prompt-injected instruction
    in a symptom note becomes an authorisation bypass. This test is the tripwire.
    """
    banned = {"patient_id", "patient", "user_id", "profile_id", "subject_id"}
    for spec in TOOL_SPECS:
        properties = set(spec["parameters"].get("properties", {}))
        assert not (properties & banned), f"{spec['name']} exposes a patient selector"


def test_every_advertised_tool_exists_and_is_bound_to_one_record():
    tools = RecordTools(db=None, profile=None)
    dispatch = clinician_assistant._dispatch(tools)
    assert {s["name"] for s in TOOL_SPECS} == set(dispatch)

    for name, handler in dispatch.items():
        params = set(inspect.signature(handler).parameters)
        assert not (params & {"patient_id", "profile", "db"}), name


async def test_tools_read_only_the_patient_they_were_built_for(
    session_factory, client, clinician, assigned_patient
):
    from app.models.clinical import VitalsRecord
    from app.models.user import PatientProfile, User
    from app.core.security import hash_password

    # A second patient with a distinctive reading.
    async with session_factory() as db:
        other_user = User(email="two@test.com", hashed_password=hash_password("x" * 12),
                          full_name="Other Patient", role=UserRole.PATIENT)
        db.add(other_user)
        await db.flush()
        other = PatientProfile(user_id=other_user.id)
        db.add(other)
        await db.flush()
        db.add(VitalsRecord(patient_id=other.id, systolic=199, diastolic=115))
        db.add(VitalsRecord(patient_id=assigned_patient["profile_id"],
                            systolic=118, diastolic=76))
        await db.commit()
        subject = await db.get(PatientProfile, assigned_patient["profile_id"])

    async with session_factory() as db:
        subject = await db.get(PatientProfile, assigned_patient["profile_id"])
        tools = RecordTools(db, subject)
        readings = (await tools.vitals())["readings"]

    systolics = {r["systolic"] for r in readings}
    assert 118 in systolics
    assert 199 not in systolics


# --- access control ---------------------------------------------------------
async def test_a_patient_cannot_use_the_clinician_assistant(client, assigned_patient):
    r = await client.post(
        f"/api/v1/assistant/patients/{assigned_patient['profile_id']}",
        json={"question": "summarise me"}, headers=assigned_patient["headers"],
    )
    assert r.status_code == 403


async def test_an_unassigned_clinician_gets_404(
    client, session_factory, clinician, assigned_patient
):
    await _make_user(session_factory, "doc2@test.com", UserRole.CLINICIAN, "Dr Two")
    other = await auth_headers(client, "doc2@test.com")
    r = await client.post(
        f"/api/v1/assistant/patients/{assigned_patient['profile_id']}",
        json={"question": "anything"}, headers=other,
    )
    assert r.status_code == 404


# --- behaviour with no model configured -------------------------------------
async def test_offline_answer_is_the_record_and_says_so(
    client, clinician, assigned_patient
):
    r = await client.post(
        f"/api/v1/assistant/patients/{assigned_patient['profile_id']}",
        json={"question": "How is she doing?"}, headers=clinician["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generated"] is False
    assert "no language model" in body["answer"].lower()
    assert "get_vitals" in body["tools_used"]


async def test_an_absence_is_reported_rather_than_invented(
    client, clinician, assigned_patient
):
    r = await client.post(
        f"/api/v1/assistant/patients/{assigned_patient['profile_id']}",
        json={"question": "walk test?"}, headers=clinician["headers"],
    )
    answer = r.json()["answer"]
    assert "No six-minute walk test on record." in answer
    assert "No vitals logged" in answer


async def test_the_thread_is_persisted_and_clearable(client, clinician, assigned_patient):
    pid = assigned_patient["profile_id"]
    await client.post(f"/api/v1/assistant/patients/{pid}",
                      json={"question": "first question"}, headers=clinician["headers"])

    thread = (await client.get(f"/api/v1/assistant/patients/{pid}",
                               headers=clinician["headers"])).json()
    assert [t["role"] for t in thread] == ["user", "assistant"]
    assert thread[0]["content"] == "first question"
    assert thread[1]["tools_used"]

    assert (await client.delete(f"/api/v1/assistant/patients/{pid}",
                                headers=clinician["headers"])).status_code == 204
    assert (await client.get(f"/api/v1/assistant/patients/{pid}",
                             headers=clinician["headers"])).json() == []


async def test_threads_do_not_bleed_between_patients(
    client, session_factory, clinician, assigned_patient, admin
):
    """Two patients, one clinician: each thread must stay its own."""
    from app.models.user import PatientProfile
    from sqlalchemy import select

    await _make_user(session_factory, "two@test.com", UserRole.PATIENT, "Patient Two")
    async with session_factory() as db:
        second = (await db.execute(
            select(PatientProfile).join(PatientProfile.user).where(
                PatientProfile.user.has(email="two@test.com")
            )
        )).scalar_one()
        second_id = second.id

    await client.patch(
        f"/api/v1/clinician/patients/{second_id}/assignment",
        json={"clinician_id": clinician["user_id"]}, headers=admin["headers"],
    )

    await client.post(f"/api/v1/assistant/patients/{assigned_patient['profile_id']}",
                      json={"question": "about the first"}, headers=clinician["headers"])

    other_thread = (await client.get(f"/api/v1/assistant/patients/{second_id}",
                                     headers=clinician["headers"])).json()
    assert other_thread == []


async def test_a_question_that_is_too_long_is_refused(client, clinician, assigned_patient):
    r = await client.post(
        f"/api/v1/assistant/patients/{assigned_patient['profile_id']}",
        json={"question": "x" * 5000}, headers=clinician["headers"],
    )
    assert r.status_code == 422

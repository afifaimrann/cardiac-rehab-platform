"""Cardiac rehabilitation guidance corpus.

A small, curated, in-repository knowledge base. Every passage carries a source
label, and answers cite the passages they were built from, so a patient (or a
reviewing clinician) can see exactly what the assistant drew on.

The content is general patient-education material paraphrased from standard
cardiac rehabilitation guidance. It is illustrative for this project and is not
a substitute for the patient's own care plan.
"""
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Passage:
    id: str
    title: str
    source: str
    text: str


CORPUS: List[Passage] = [
    Passage(
        "exercise-intensity", "How hard should I exercise?", "Programme handbook, s.2.1",
        "During phase II rehabilitation most people are asked to work at a moderate "
        "intensity: you should be able to talk in short sentences but not sing. On the "
        "Borg scale of perceived exertion this is roughly 11 to 14 out of 20. If you "
        "cannot speak comfortably, slow down. Working above 17 is above the intended "
        "range and should be reported to your rehabilitation team.",
    ),
    Passage(
        "exercise-frequency", "How often and how long should I exercise?", "Programme handbook, s.2.2",
        "A typical starting prescription is three sessions a week of about 30 minutes, "
        "which may be broken into shorter blocks. Consistency matters more than "
        "intensity: three moderate sessions each week produce better outcomes than one "
        "hard session. Your own plan may differ, and your plan takes precedence.",
    ),
    Passage(
        "warmup-cooldown", "Warming up and cooling down", "Programme handbook, s.2.3",
        "Begin every session with five to ten minutes of gentle movement and finish with "
        "a similar cool-down. Stopping abruptly after exertion can cause dizziness and "
        "puts unnecessary strain on the heart.",
    ),
    Passage(
        "stop-exercise", "When to stop exercising immediately", "Programme handbook, s.3.1",
        "Stop exercising and seek urgent medical help if you experience chest pain, "
        "pressure or tightness, severe breathlessness, dizziness or fainting, an "
        "irregular or racing heartbeat, or cold sweats. These symptoms during exercise "
        "always need assessment. Do not attempt to push through them.",
    ),
    Passage(
        "chest-pain", "Chest pain and angina", "Programme handbook, s.3.2",
        "Any new, worsening, or unexplained chest pain needs medical assessment. Chest "
        "pain that comes on at rest, lasts more than a few minutes, or is accompanied by "
        "sweating, nausea, or breathlessness may indicate a heart attack and is a medical "
        "emergency: call emergency services rather than waiting for a scheduled "
        "appointment.",
    ),
    Passage(
        "blood-pressure-targets", "Blood pressure in rehabilitation", "Programme handbook, s.4.1",
        "Many rehabilitation programmes aim to keep resting blood pressure below 140/90 "
        "mmHg, with a tighter target for some patients. A reading at or above 180/120 "
        "mmHg is a hypertensive crisis and needs urgent attention. Take readings while "
        "seated and rested for five minutes, with your arm supported at heart level.",
    ),
    Passage(
        "measuring-bp", "How to measure your blood pressure at home", "Programme handbook, s.4.2",
        "Sit with your back supported and feet flat, rest for five minutes, and avoid "
        "caffeine or exercise for thirty minutes beforehand. Take two readings a minute "
        "apart and record both. Measuring at the same time each day makes the trend more "
        "useful than any single reading.",
    ),
    Passage(
        "heart-rate", "Understanding your target heart rate", "Programme handbook, s.4.3",
        "Your rehabilitation team may give you a heart rate ceiling for exercise, based "
        "on an exercise test or on your medication. Beta blockers lower both resting and "
        "exercise heart rate, so a target calculated from age alone can be misleading if "
        "you take them. Use the ceiling your team gave you.",
    ),
    Passage(
        "medication-adherence", "Taking your medication", "Programme handbook, s.5.1",
        "Take cardiac medication exactly as prescribed, including on days you feel well. "
        "Do not stop or change a dose without speaking to your doctor: stopping beta "
        "blockers or antiplatelet medication abruptly can be dangerous. If you miss a "
        "dose, ask your pharmacist rather than doubling up.",
    ),
    Passage(
        "medication-side-effects", "Common medication side effects", "Programme handbook, s.5.2",
        "Tiredness, dizziness on standing, and a slower pulse are common early effects of "
        "beta blockers and often settle. Persistent dizziness, fainting, or a resting "
        "pulse below 50 should be reported. A dry persistent cough can occur with ACE "
        "inhibitors and is worth mentioning at your next review.",
    ),
    Passage(
        "diet", "Eating for heart health", "Programme handbook, s.6.1",
        "Aim for a diet built around vegetables, fruit, whole grains, pulses, and fish, "
        "with limited processed meat, refined sugar, and salt. Reducing salt helps blood "
        "pressure; most excess salt comes from processed food rather than the salt "
        "shaker. Small sustained changes outperform short restrictive diets.",
    ),
    Passage(
        "fluid-weight", "Weight and fluid retention", "Programme handbook, s.6.2",
        "For patients with heart failure, a sudden weight gain of more than two "
        "kilograms over two or three days can indicate fluid retention and should be "
        "reported. Weigh yourself at the same time each morning, after using the toilet "
        "and before breakfast.",
    ),
    Passage(
        "swelling", "Swollen ankles and legs", "Programme handbook, s.6.3",
        "New or worsening swelling in the ankles, legs, or abdomen, particularly with "
        "breathlessness when lying flat, can be a sign that the heart is not pumping "
        "effectively. Report this to your care team promptly rather than waiting.",
    ),
    Passage(
        "smoking", "Stopping smoking", "Programme handbook, s.7.1",
        "Stopping smoking is the single most effective thing most cardiac patients can do "
        "to reduce their risk of a further event, and the benefit begins within days. "
        "Combining medication with behavioural support is considerably more effective "
        "than willpower alone. Ask your team for a referral.",
    ),
    Passage(
        "alcohol", "Alcohol", "Programme handbook, s.7.2",
        "If you drink, keep within national low-risk guidance and have several alcohol-free "
        "days a week. Alcohol raises blood pressure, interacts with several cardiac "
        "medications, and can trigger irregular heart rhythms.",
    ),
    Passage(
        "return-to-work", "Returning to work", "Programme handbook, s.8.1",
        "Many people return to work within four to twelve weeks, depending on the event, "
        "the treatment, and how physical the job is. A phased return is often easier to "
        "sustain than a full-time restart. Discuss timing with your cardiologist before "
        "committing to a date.",
    ),
    Passage(
        "driving", "Driving after a cardiac event", "Programme handbook, s.8.2",
        "There is usually a minimum period before you may drive again, and it differs by "
        "event, by treatment, and by licence type, with longer restrictions for vocational "
        "licences. Check the rules that apply where you live and confirm with your "
        "cardiologist before driving.",
    ),
    Passage(
        "sexual-activity", "Resuming sexual activity", "Programme handbook, s.8.3",
        "Most people can resume sexual activity once they can manage moderate exertion, "
        "such as climbing two flights of stairs, without chest pain or undue "
        "breathlessness. If you take nitrates, do not use erectile dysfunction medication: "
        "the combination can cause a dangerous drop in blood pressure.",
    ),
    Passage(
        "wound-care", "Caring for a surgical wound", "Programme handbook, s.9.1",
        "Keep a sternal or graft wound clean and dry, and avoid lifting more than a few "
        "kilograms or pushing through your arms for the period your surgical team "
        "specified. Report increasing redness, discharge, a clicking sternum, or fever.",
    ),
    Passage(
        "mood", "Mood after a cardiac event", "Programme handbook, s.10.1",
        "Low mood, anxiety, and fear of exertion are common after a cardiac event and are "
        "not a sign of weakness. They also affect recovery: people who get support tend "
        "to complete rehabilitation more often. Tell your team if this is affecting you; "
        "support is part of the programme.",
    ),
    Passage(
        "sleep", "Sleep and recovery", "Programme handbook, s.10.2",
        "Disturbed sleep is common early in recovery. Keep a regular schedule, limit "
        "caffeine after midday, and raise loud snoring or daytime sleepiness with your "
        "team, as sleep apnoea is common in cardiac patients and is treatable.",
    ),
]

CORPUS_BY_ID = {p.id: p for p in CORPUS}

"""Emergency detection for patient questions.

A question describing symptoms in progress is not a retrieval problem. It is
intercepted before the model sees it, answered with fixed escalation advice, and
flagged for the care team -- the assistant must never be the reason someone
waits.

Deliberately keyword-based and deliberately over-inclusive: a false positive
costs a patient one unnecessary reassurance, a false negative costs far more.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from app.services.language import uses_bengali

# Phrases describing something happening now, not asked in the abstract.
EMERGENCY_PATTERNS = [
    r"\bchest\b(?:\s+\w+){0,2}\s+(pain|pressure|tightness|tight|ache)\b",
    r"\bchest (pain|pressure|tightness|tight)\b",
    r"\b(crushing|squeezing) (pain|feeling)\b",
    r"\bpain (in|down) my (arm|jaw|neck|back)\b",
    r"\bcan'?t breathe\b",
    r"\bcannot breathe\b",
    r"\b(severe|really) (breathless|short of breath)\b",
    r"\bstruggling to breathe\b",
    r"\b(fainted|passed out|blacked out|collapsed)\b",
    r"\babout to faint\b",
    r"\bheart (racing|pounding) and\b",
    r"\bcold sweat\b",
    r"\bnumb(ness)? in my (arm|face)\b",
    r"\bslurred speech\b",
]

# Phrasings that indicate a general question rather than a live symptom.
INFORMATIONAL_MARKERS = [
    r"\bwhat (should|do) i do if\b",
    r"\bwhat (does|is)\b",
    r"\bwhy (does|do|is)\b",
    r"\bhow (do|does|can|long|often)\b",
    r"\bis it normal\b",
    r"\bcan i\b",
    r"\bshould i be (worried|concerned) about .* in (general|future)\b",
]

# --------------------------------------------------------------------------
# Bengali
# --------------------------------------------------------------------------
# Written in Bengali script and in transliteration, because patients type both
# and a Latin-keyboard "buke betha" must not slip past a Bengali-script matcher.
#
# PENDING NATIVE-SPEAKER REVIEW: these were drafted from standard medical
# phrasing. Regional and colloquial variants are the likeliest gap, and a missed
# variant here is a missed emergency.
# Bangla puts intensifiers and time words between the body part and the
# symptom -- "বুকে অনেক ব্যথা", "বুকে আজকে খুব ব্যথা" -- so the parts are
# allowed to be a few words apart rather than adjacent. Requiring adjacency
# missed a real patient message in testing.
_GAP = r"(?:\s+\S+){0,3}\s*"

_CHEST = r"(?:বুক|বুকে|বুকের|চেস্ট|বুকটা)"
_PAIN = r"(?:ব্যথা|ব্যাথা|বেথা|ব্যাথ|যন্ত্রণা|চিনচিন)"

BENGALI_EMERGENCY_PATTERNS = [
    # Chest pain, with the two halves optionally separated.
    _CHEST + _GAP + _PAIN,
    _PAIN + _GAP + _CHEST,
    _CHEST + _GAP + r"(?:চাপ|ধরেছে|ভার|চাপ\s*লাগছে)",
    _CHEST + _GAP + r"(?:জ্বালা|জ্বলছে|কষ্ট)",
    r"বুক" + _GAP + r"ধড়?ফড়?",
    # Breathing
    r"শ্বাস\s*কষ্ট", r"শ্বাসকষ্ট",
    r"শ্বাস" + _GAP + r"(?:কষ্ট|নিতে\s*পারছি\s*না|আটকে)",
    r"(?:দম|নিঃশ্বাস)" + _GAP + r"(?:বন্ধ|আটকে)",
    # Dizziness and fainting
    r"মাথা" + _GAP + r"ঘ(?:ু|ো)র",
    r"অজ্ঞান", r"জ্ঞান\s*হারা", r"বেহুঁশ", r"সেন্সলেস",
    # Associated features
    r"ঠান্ডা\s*ঘাম", r"ঘাম\s*(?:দিচ্ছে|হচ্ছে)",
    r"(?:বাম|বাঁ|ডান)\s*হাতে?" + _GAP + _PAIN,
    r"(?:ঘাড়|চোয়াল|গলা)ে?" + _GAP + _PAIN,
    r"হার্ট\s*অ্যা?টাক", r"হৃদরোগ", r"স্ট্রোক",
]

# Transliterated forms. Spelling is not standardised, so each pattern allows the
# common vowel substitutions rather than listing every spelling separately.
TRANSLITERATED_EMERGENCY_PATTERNS = [
    # Transliteration is not standardised, so the pain word is matched as a set
    # of observed spellings and the body part is allowed to be English.
    # Same gap tolerance in transliteration: "buke onek betha".
    r"\b(?:buk|buke|buker|bukey|chest)(?:\s+\w+){0,3}\s+(?:betha|byatha|byetha|batha|bytha|chap)\b",
    r"\b(betha|byatha|byetha)\s*(buke|chest)\b",
    r"\bbuk[ey]?\s*(dhor?for|dhar?far|dhukdhuk)",
    r"\b(sh?wash?|nishash)\s*kosto\b",
    r"\bdom\s*(bondho|atke)\b",
    r"\bmatha\s*ghur",
    r"\bogg?yan\b", r"\bbehush\b", r"\bsenseless\b",
    r"\bthanda\s*gham\b",
    r"\b(bam|ban)\s*hate?\s*(betha|byatha)\b",
    r"\bheart\s*attack\b", r"\bstroke\b",
]

# Bengali phrasings that mark a general question rather than a live symptom.
BENGALI_INFORMATIONAL_MARKERS = [
    r"কি\s*করব",
    r"কী\s*করব",
    r"কেন\s*হয়",
    r"কিভাবে",
    r"কীভাবে",
    r"হলে\s*কি",
    r"কি\s*করা\s*উচিত",
]

# Words indicating the symptom is present now, which override the markers above.
BENGALI_PRESENT_TENSE = [
    r"হচ্ছে", r"করছে", r"লাগছে", r"পারছি\s*না", r"এখন", r"হঠাৎ",
    r"\bhocche\b", r"\bkorche\b", r"\blagche\b", r"\bekhon\b",
]

EMERGENCY_RESPONSE = (
    "I can't help with symptoms that are happening right now, and this needs a "
    "person rather than an app.\n\n"
    "**If you are having chest pain, severe breathlessness, fainting, or symptoms "
    "of a heart attack or stroke, call your local emergency number now.** Do not "
    "drive yourself.\n\n"
    "If the symptom has passed but was new or frightening, contact your "
    "rehabilitation team or doctor today rather than waiting for your next "
    "appointment.\n\n"
    "I've let your care team know you asked about this."
)


@dataclass(frozen=True)
class GuardrailVerdict:
    is_emergency: bool
    matched: List[str]
    response: Optional[str] = None


EMERGENCY_RESPONSE_BN = (
    "এখনই যে উপসর্গ হচ্ছে সে বিষয়ে আমি সাহায্য করতে পারব না — এর জন্য একজন "
    "মানুষ দরকার, অ্যাপ নয়।\n\n"
    "**যদি এখন বুকে ব্যথা, তীব্র শ্বাসকষ্ট, জ্ঞান হারানো, বা হার্ট অ্যাটাক "
    "কিংবা স্ট্রোকের লক্ষণ থাকে, তাহলে এখনই জরুরি নম্বরে ফোন করুন।** নিজে "
    "গাড়ি চালাবেন না।\n\n"
    "উপসর্গ চলে গিয়ে থাকলেও, যদি সেটা নতুন বা ভয় পাওয়ার মতো হয়, তাহলে পরের "
    "অ্যাপয়েন্টমেন্টের জন্য অপেক্ষা না করে আজই আপনার রিহ্যাবিলিটেশন টিম বা "
    "ডাক্তারের সঙ্গে যোগাযোগ করুন।\n\n"
    "আপনি এ বিষয়ে জিজ্ঞাসা করেছেন, সেটা আমি আপনার কেয়ার টিমকে জানিয়ে দিয়েছি।"
)


def check(question: str) -> GuardrailVerdict:
    """Emergency detection across English, Bengali and transliterated Bengali.

    The response is returned in the language the patient wrote in: escalation
    advice nobody can read is not escalation advice.
    """
    text = question.lower()
    bengali = uses_bengali(question)

    matched = [p for p in EMERGENCY_PATTERNS if re.search(p, text)]
    matched += [p for p in BENGALI_EMERGENCY_PATTERNS if re.search(p, question)]
    matched += [p for p in TRANSLITERATED_EMERGENCY_PATTERNS if re.search(p, text)]
    if not matched:
        return GuardrailVerdict(False, [])

    response = EMERGENCY_RESPONSE_BN if bengali else EMERGENCY_RESPONSE

    present_tense = re.search(
        r"\b(i am|i'm|im|right now|currently|having|feeling|got)\b", text
    ) or any(re.search(p, question) for p in BENGALI_PRESENT_TENSE)

    informational = any(re.search(m, text) for m in INFORMATIONAL_MARKERS) or any(
        re.search(m, question) for m in BENGALI_INFORMATIONAL_MARKERS
    )

    # A clearly hypothetical question gets a normal answer, but present-tense
    # phrasing always wins: "বুকে ব্যথা হলে কি করব" is a question, while
    # "বুকে ব্যথা হচ্ছে, কি করব" is someone telling us it is happening now.
    if informational and not present_tense:
        return GuardrailVerdict(False, [])

    return GuardrailVerdict(True, matched, response)

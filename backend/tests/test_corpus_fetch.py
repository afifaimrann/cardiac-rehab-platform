"""Feed parsing, filtering and cleaning.

The network fetch itself is not tested (it depends on a live third-party feed);
everything that happens to the bytes afterwards is, against a synthetic feed
shaped like the real one.
"""
import pytest

from scripts.fetch_corpus import clean, is_excluded, iter_topics, slugify, wanted

SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<health-topics total="4">
  <health-topic title="Heart Attack" url="https://medlineplus.gov/heartattack.html"
                language="English" id="1">
    <also-called>Myocardial infarction</also-called>
    <also-called>MI</also-called>
    <full-summary>&lt;p&gt;A heart attack happens when blood flow to the heart is
    blocked.&lt;/p&gt;&lt;p&gt;Symptoms include chest pain &amp;amp; shortness of
    breath.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Call 911&lt;/li&gt;&lt;/ul&gt;</full-summary>
    <group url="https://medlineplus.gov/heartandcirculation.html">Heart and Circulation</group>
  </health-topic>

  <health-topic title="Ataque al corazon" url="https://medlineplus.gov/spanish/x.html"
                language="Spanish" id="2">
    <full-summary>Contenido en espanol que no debe incluirse en el corpus ingles.</full-summary>
    <group>Corazon</group>
  </health-topic>

  <health-topic title="Congenital Heart Defects" url="https://medlineplus.gov/chd.html"
                language="English" id="3">
    <full-summary>&lt;p&gt;Congenital heart defects are present at birth and are
    outside the scope of an adult rehabilitation programme corpus.&lt;/p&gt;</full-summary>
    <group>Heart and Circulation</group>
  </health-topic>

  <health-topic title="Quitting Smoking" url="https://medlineplus.gov/quittingsmoking.html"
                language="English" id="4">
    <full-summary>&lt;p&gt;Stopping smoking lowers your risk of another cardiac
    event, and the benefit begins within days of your last cigarette.&lt;/p&gt;</full-summary>
    <group>Health and Wellness</group>
  </health-topic>
</health-topics>
"""


def test_only_english_topics_are_parsed():
    titles = [t["title"] for t in iter_topics(SAMPLE_FEED)]
    assert "Heart Attack" in titles
    assert "Ataque al corazon" not in titles


def test_summary_markup_is_stripped_and_entities_decoded():
    topic = next(t for t in iter_topics(SAMPLE_FEED) if t["title"] == "Heart Attack")
    text = clean(topic["summary"])
    assert "<p>" not in text and "&amp;" not in text and "&lt;" not in text
    assert "chest pain & shortness of breath" in text
    assert "- Call 911" in text
    # Paragraph breaks survive; runaway blank lines do not.
    assert "\n\n" in text and "\n\n\n" not in text


def test_cardiovascular_group_is_kept():
    assert wanted("Heart Attack", ["Heart and Circulation"])


def test_relevant_topic_outside_the_group_is_kept_by_title():
    assert wanted("Quitting Smoking", ["Health and Wellness"])


def test_irrelevant_topic_is_dropped():
    assert not wanted("Ear Infections", ["Ears and Hearing"])


def test_paediatric_and_congenital_topics_are_excluded():
    assert is_excluded("Congenital Heart Defects")
    assert is_excluded("High Blood Pressure in Children")
    assert not is_excluded("High Blood Pressure")
    # Exclusion wins even when the group matches.
    assert not wanted("Congenital Heart Defects", ["Heart and Circulation"])


def test_also_called_aliases_are_captured():
    topic = next(t for t in iter_topics(SAMPLE_FEED) if t["title"] == "Heart Attack")
    assert topic["also_called"] == ["Myocardial infarction", "MI"]


def test_slugify_produces_safe_filenames():
    assert slugify("Heart Attack") == "heart-attack"
    assert slugify("Blood Pressure / Hypertension!") == "blood-pressure-hypertension"
    assert len(slugify("x" * 200)) <= 80


@pytest.mark.parametrize(
    "title",
    [
        "Acute Lymphocytic Leukemia", "Chronic Myeloid Leukemia", "Leukemia",
        "Hemophilia", "Sickle Cell Disease", "Thalassemia",
        "Bleeding Disorders", "Platelet Disorders",
        "Blood Transfusion and Donation", "Blood Count Tests",
    ],
)
def test_haematology_and_oncology_topics_are_excluded(title):
    """The MedlinePlus 'Blood, Heart and Circulation' group includes blood
    cancers. Surfacing a leukemia page to a cardiac rehab patient is alarming,
    not merely irrelevant."""
    assert is_excluded(title)
    assert not wanted(title, ["Blood, Heart and Circulation"])


@pytest.mark.parametrize(
    "title", ["Angina", "Heart Failure", "High Blood Pressure", "Cardiac Rehabilitation"]
)
def test_cardiac_topics_survive_the_exclusions(title):
    assert not is_excluded(title)

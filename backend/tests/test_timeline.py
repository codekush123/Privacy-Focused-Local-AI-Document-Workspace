"""Timeline: the model proposes dated events, the app verifies and sorts them."""
from __future__ import annotations

import pytest

from app.services.evaluation.suite import load_suite
from app.services.features import timeline
from app.services.features.timeline import TimelineEventSpec, TimelineSpec, date_forms, verify_events


def E(date, date_text, title, quote, doc, location, detail="x"):
    return TimelineEventSpec(date=date, date_text=date_text, title=title, detail=detail, quote=quote,
                             source_document=doc, source_location=location)


@pytest.fixture(scope="module")
def corpora():
    s = load_suite()
    return s.corpora["en"].documents, s.corpora["fi"].documents


def statuses(spec, docs):
    return {e.title: e.status for e in verify_events(spec, docs).events}


def test_real_dates_are_verified_and_invented_ones_flagged(corpora):
    en, _fi = corpora
    spec = TimelineSpec(events=[
        E("2026-08-14", "14 August 2026", "Hietasaari commissioning moved",
          "Commissioning has therefore been moved from 30 April 2026 to 14 August 2026", 2, "Heading: Project status"),
        E("2026-03-15", "15 March 2026", "Invented event", "nothing like this", 1, "Page 3"),
        E("2026-03-20", "20 March 2026", "Unknown source", "nothing like this", 9, "Page 1"),
        E("2026-13-40", "soon", "Broken date", "", 1, "Page 1"),
    ])
    assert statuses(spec, en) == {
        "Hietasaari commissioning moved": "verified",
        "Invented event": "date_not_in_source",
        "Unknown source": "citation_unresolved",  # source 9 does not exist and the date is nowhere
        "Broken date": "invalid_date",
    }


def test_an_unknown_source_number_is_recovered_when_the_date_is_real(corpora):
    en, _fi = corpora
    spec = TimelineSpec(events=[E("2026-04-22", "22 April 2026", "Annual general meeting",
                                  "The annual general meeting will be held in Harjuvesi", 9, "Page 1")])
    event = verify_events(spec, en).events[0]
    assert event.status == "verified" and event.citation.resolved_locator == "Page 9"


def test_a_date_must_belong_to_the_event_not_just_be_on_the_page(corpora):
    """Seen with the real model: every Finnish event got '2025', a year that appears on
    almost every page. Only the paragraph that names the event counts."""
    _en, fi = corpora
    spec = TimelineSpec(events=[
        E("2027", "syksyllä 2027", "Ristinevan tuulipuiston käyttöönotto",
          "käyttöönoton arvioidaan nyt tapahtuvan syksyllä 2027", 1, "Page 4"),
        E("2025", "2025", "Ristinevan käyttöönotto", "Ristinevan tuulipuisto", 1, "Page 4"),
    ])
    assert statuses(spec, fi) == {"Ristinevan tuulipuiston käyttöönotto": "verified",
                                  "Ristinevan käyttöönotto": "date_elsewhere"}


def test_generic_words_do_not_verify_a_wrong_date(corpora):
    """Seen with the real model: 'Kivijärvi solar park completed in 2025' shared only the
    generic words 'aurinkopuisto' and 'valmistua' with a 2025 paragraph about Haukilahti.
    Kivijärvi was completed in spring 2024, so the quote must decide."""
    _en, fi = corpora
    spec = TimelineSpec(events=[
        E("2025", "vuonna 2025", "Kivijärven aurinkopuiston valmistuminen",
          "Keväällä 2024 valmistunut Kivijärven aurinkopuisto", 1, "Page 4"),
    ])
    assert verify_events(spec, fi).events[0].status != "verified"


def test_page_number_given_as_source_number_is_recovered(corpora):
    """Seen with the real model: [S4: Page 4] for a single selected document."""
    en, _fi = corpora
    spec = TimelineSpec(events=[
        E("2025-05", "May 2025", "Haukilahti construction starts",
          "Construction of the 22 MW solar park started in May 2025", 4, "Page 4"),
    ])
    event = verify_events(spec, en[:1]).events[0]
    assert event.status == "verified" and event.citation.resolved_locator == "Page 4"


def test_a_wrong_location_is_corrected_by_the_app(corpora):
    en, _fi = corpora
    spec = TimelineSpec(events=[
        E("2026-04-22", "22 April 2026", "Annual general meeting", "The annual general meeting will be held in Harjuvesi",
          1, "Page 2"),
    ])
    event = verify_events(spec, en).events[0]
    assert event.status == "verified" and event.citation.resolved_locator == "Page 9"


def test_finnish_dates_and_english_titles_on_finnish_documents(corpora):
    _en, fi = corpora
    spec = TimelineSpec(events=[
        E("2026-08-14", "14.8.2026", "Hietasaari commissioning", "siirretty 30.4.2026:sta 14.8.2026:een", 2,
          "Heading: Hankkeiden tilanne"),
        E("2025-05", "toukokuussa 2025", "Haukilahti construction starts",
          "aurinkopuiston rakentaminen alkoi toukokuussa 2025", 1, "Page 4"),
    ])
    assert set(statuses(spec, fi).values()) == {"verified"}


def test_the_app_sorts_by_date_and_drops_duplicates(corpora):
    en, _fi = corpora
    meeting = E("2025-11-18", "18 November 2025", "Steering group meeting", "Date: 18 November 2025, 13:00-15:30",
                2, "Heading: Meeting details")
    spec = TimelineSpec(events=[
        E("2027", "autumn of 2027", "Ristineva commissioning", "commissioning is now expected in the autumn of 2027",
          1, "Page 4"),
        meeting,
        E("2025-05", "May 2025", "Haukilahti construction", "Construction of the 22 MW solar park started in May 2025",
          1, "Page 4"),
        meeting,
    ])
    result = verify_events(spec, en)
    assert [e.date for e in result.events] == ["2025-05", "2025-11-18", "2027"]
    assert [e.precision for e in result.events] == ["month", "day", "year"]
    assert result.counts == {"total": 3, "verified": 3}


def test_a_year_comes_before_its_months():
    spec = TimelineSpec(events=[E("2026-05", "May 2026", "b", "", 1, ""), E("2026", "2026", "a", "", 1, "")])
    assert [e.date for e in verify_events(spec, []).events] == ["2026", "2026-05"]


def test_the_schema_caps_the_number_of_events():
    assert TimelineSpec.model_json_schema()["properties"]["events"]["maxItems"] == timeline.MAX_EVENTS


def test_date_forms_cover_english_and_finnish():
    forms = date_forms(2026, 8, 14)
    assert {"14.8.2026", "2026-08-14", "14 august 2026", "august 14, 2026", "14. elokuu"} <= set(forms)


def test_timeline_endpoint_verifies_what_the_model_proposes(client, fixtures, monkeypatch):
    with open(fixtures / "sample.pdf", "rb") as f:
        doc = client.post("/api/documents/upload", files={"file": ("sample.pdf", f, "application/pdf")}).json()

    async def fake_structured(model, prompt, documents, **kwargs):
        assert model is TimelineSpec and "dated events" in prompt
        return TimelineSpec(events=[E("2099-01-01", "1 January 2099", "Not in the file", "", 1, "Page 1")])

    monkeypatch.setattr(timeline, "ask_structured", fake_structured)
    monkeypatch.setattr("app.routers.features.ensure_ai_allowed", lambda: None)
    r = client.post("/api/timeline", json={"document_ids": [doc["id"]], "language": "English"})
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["total"] == 1 and body["events"][0]["status"] == "date_not_in_source"

    x = client.post("/api/timeline/export", json={"events": body["events"], "document_ids": [doc["id"]]})
    assert x.status_code == 200 and x.json()["filename"].endswith(".xlsx")


def test_timeline_needs_documents(client):
    assert client.post("/api/timeline", json={"document_ids": []}).status_code == 422

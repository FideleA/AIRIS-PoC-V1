import inspect
import re
from urllib.parse import urlparse
from unittest.mock import Mock

import app
from data_sources import (
    ACCESS_DATE,
    ATTRIBUTIONS,
    DATA_SOURCES,
    FIELD_LABELS,
    NRW_ATTRIBUTION_TEXT,
    UNKNOWN,
    external_urls,
)


def test_every_source_uses_all_required_fields_in_order():
    assert len(FIELD_LABELS) == 15
    assert len(DATA_SOURCES) == 7
    for record in DATA_SOURCES:
        assert tuple(record) == FIELD_LABELS
        assert all(record[label].text.strip() for label in FIELD_LABELS)
        assert record["Date accessed or retrieved"].text == ACCESS_DATE


def test_required_source_identifiers_and_urls_are_present():
    combined = "\n".join(
        value.text
        for record in DATA_SOURCES
        for value in record.values()
    )
    urls = set(external_urls())
    assert "bb732e4f-689b-4f95-8d0c-12ec8c0dcfe5" in combined
    assert "inspire-nrw:FloodRiskAssessmentWales" in combined
    assert {
        "https://datamap.gov.wales/layergroups/inspire-nrw%3AFloodRiskAssessmentWales/metadata_detail",
        "https://datamap.gov.wales/layers/inspire-nrw%3ANRW_FLOOD_RISK_FROM_RIVERS/metadata_detail",
        "https://datamap.gov.wales/layers/inspire-nrw%3ANRW_FLOOD_RISK_FROM_SEA/metadata_detail",
        "https://datamap.gov.wales/layers/inspire-nrw%3ANRW_FLOOD_RISK_FROM_SURFACE_WATER_SMALL_WATERCOURSES/metadata_detail",
        "https://open-meteo.com/en/docs",
        "https://open-meteo.com/en/licence",
        "https://open-meteo.com/",
    }.issubset(urls)


def test_external_urls_are_valid_https_urls():
    for url in external_urls():
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc
        assert " " not in url


def test_attributions_include_required_legal_statements_and_links():
    attribution_text = "\n".join(item.text for item in ATTRIBUTIONS)
    attribution_urls = {
        link.url for item in ATTRIBUTIONS for link in item.links
    }
    assert NRW_ATTRIBUTION_TEXT in attribution_text
    assert "Welsh Government" in attribution_text
    assert "Office for National Statistics" in attribution_text
    assert "Open Charge Map" in attribution_text
    assert "Weather data by Open-Meteo.com" in attribution_text
    assert "https://open-meteo.com/" in attribution_urls


def test_records_do_not_render_absolute_paths_or_unexplained_placeholders():
    combined = "\n".join(
        value.text
        for record in DATA_SOURCES
        for value in record.values()
    )
    assert not re.search(r"(?:^|\s)[A-Za-z]:[\\/]", combined)
    assert "/Users/" not in combined
    assert UNKNOWN in combined
    for record in DATA_SOURCES:
        assert all(value.text != UNKNOWN for value in record.values())


def test_data_source_renderer_nests_records_in_one_collapsed_parent(monkeypatch):
    expander = Mock()
    expander.__enter__ = Mock(return_value=expander)
    expander.__exit__ = Mock(return_value=False)
    expander_call = Mock(return_value=expander)
    rendered = []
    monkeypatch.setattr(app.st, "header", Mock())
    monkeypatch.setattr(app.st, "caption", Mock())
    monkeypatch.setattr(app.st, "expander", expander_call)
    monkeypatch.setattr(
        app.st,
        "markdown",
        lambda text, **kwargs: rendered.append((text, kwargs)),
    )

    app.render_data_sources()

    app.st.header.assert_called_once_with("Data Sources")
    assert expander_call.call_count == len(DATA_SOURCES) + 1
    assert expander_call.call_args_list[0].args == ("View Data Sources",)
    assert expander_call.call_args_list[0].kwargs == {"expanded": False}
    child_calls = expander_call.call_args_list[1:]
    assert [call.args[0] for call in child_calls] == [
        record["Dataset or service name"].text for record in DATA_SOURCES
    ]
    assert all(call.kwargs == {"expanded": False} for call in expander_call.call_args_list)
    html = "\n".join(text for text, _ in rendered)
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html
    assert all(f"<strong>{label}</strong>" in html for label in FIELD_LABELS)
    renderer_source = inspect.getsource(app.render_data_sources)
    assert renderer_source.count('st.expander("View Data Sources"') == 1
    assert renderer_source.count("for record in DATA_SOURCES") == 1
    assert renderer_source.index('st.expander("View Data Sources"') < (
        renderer_source.index("for record in DATA_SOURCES")
    )


def test_data_sources_precede_attributions_in_main_page():
    source = inspect.getsource(app.main)
    assert source.index("render_data_sources()") < source.index(
        "render_data_attributions()"
    )
    assert '"Data attribution and licences"' not in source

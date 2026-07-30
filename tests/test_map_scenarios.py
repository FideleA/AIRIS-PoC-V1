import pandas as pd
import pytest
from shapely.geometry import box
import app

from app import (
    MAP_COMPONENT_KEY,
    add_scenario_once,
    build_airis_map,
    build_scenario_record,
    clear_scenarios,
    coordinates_within_cardiff,
    next_scenario_number,
    contribution_dataframe,
    portfolio_metrics,
    remove_scenario,
    render_airis_map,
    scenario_comparison_table,
    scenario_current_contributions,
    station_result_by_id,
    truncate_map_label,
    valid_global_coordinates,
)


WEATHER = {
    "current_temperature_c": 18.0,
    "forecast_max_temperature_c": [20, 21, 22, 23, 24, 25, 27],
    "seven_day_max_temperature_c": 27.0,
    "retrieved_at": "2026-07-21T00:00:00Z",
    "source": "Open-Meteo",
}


def charger_result(name="Park Place", station_id="airis_internal"):
    row = pd.Series(
        {
            "station_id": station_id,
            "station_name": name,
            "operator_name": "Osprey Charging",
            "postcode": "CF10 3RL",
            "latitude": 51.485936,
            "longitude": -3.176613,
        }
    )
    current = {"overall_score": 20.0, "risk_band": "very_low"}
    forecast = {"overall_score": 27.5, "risk_band": "low"}
    return {
        "station_id": station_id,
        "row": row,
        "current": current,
        "forecast": forecast,
        "error": None,
        "weather": WEATHER,
    }


def scenario(scenarios=None, **changes):
    values = {
        "latitude": 51.48,
        "longitude": -3.18,
        "flood_score": 50,
        "deprivation_score": 40,
        "weather": WEATHER,
    }
    values.update(changes)
    return build_scenario_record(scenarios or [], **values)


def test_charger_tooltip_contains_name_only_and_not_station_id():
    rendered = build_airis_map([charger_result()]).get_root().render()
    assert "Park Place" in rendered
    assert "airis_internal" not in rendered
    assert '"permanent": true' not in rendered


def test_selected_charger_gets_one_persistent_truncated_name_label():
    long_name = "A Charger Name That Is Deliberately Much Longer Than The Map Label"
    rendered = build_airis_map(
        [charger_result(long_name)], selected_station_id="airis_internal"
    ).get_root().render()
    assert '"permanent": true' in rendered
    assert truncate_map_label(long_name) in rendered
    assert long_name in rendered  # Full name remains in hover tooltip and popup.
    assert "airis_internal" not in rendered


def test_stored_marker_popup_includes_score_risk_and_timestamp():
    result = charger_result()
    result["current"]["calculated_at"] = "2026-07-30T12:45:00+00:00"
    rendered = build_airis_map([result]).get_root().render()
    assert "Score: 20.0" in rendered
    assert "Risk: Very low risk" in rendered
    assert "Last calculated:" in rendered


def test_proposed_marker_is_absent_until_a_scenario_exists():
    rendered = build_airis_map([charger_result()], scenarios=[]).get_root().render()
    assert "Proposed Site 1" not in rendered
    assert "manually supplied scenario inputs" not in rendered


def test_one_and_multiple_proposed_sites_are_added_with_sequential_labels():
    scenarios = []
    processed = set()
    first = scenario(scenarios)
    assert add_scenario_once(scenarios, processed, first, "submission-1")
    second = scenario(scenarios, flood_score=65)
    assert add_scenario_once(scenarios, processed, second, "submission-2")
    assert [item["label"] for item in scenarios] == [
        "Proposed Site 1",
        "Proposed Site 2",
    ]
    assert next_scenario_number(scenarios) == 3


def test_duplicate_rerun_submission_does_not_add_an_extra_scenario():
    scenarios = []
    processed = set()
    item = scenario(scenarios)
    assert add_scenario_once(scenarios, processed, item, "same-event")
    assert not add_scenario_once(scenarios, processed, item, "same-event")
    assert len(scenarios) == 1


def test_identical_coordinates_are_allowed_with_intentionally_different_assumptions():
    scenarios = []
    processed = set()
    add_scenario_once(scenarios, processed, scenario(scenarios), "one")
    add_scenario_once(
        scenarios,
        processed,
        scenario(scenarios, flood_score=90, deprivation_score=70),
        "two",
    )
    assert len(scenarios) == 2
    assert scenarios[0]["current_score"] != scenarios[1]["current_score"]


def test_scenarios_persist_in_session_collection_and_can_be_removed_or_cleared():
    scenarios = [scenario()]
    scenarios.append(scenario(scenarios, flood_score=65))
    persisted_reference = scenarios
    assert remove_scenario(scenarios, "1")
    assert scenarios is persisted_reference
    assert [item["scenario_id"] for item in scenarios] == ["2"]
    clear_scenarios(scenarios)
    assert scenarios == []


def test_explicit_session_counter_prevents_label_reuse_after_removal():
    scenarios = [scenario()]
    second = build_scenario_record(
        scenarios,
        51.49,
        -3.19,
        50,
        50,
        WEATHER,
        scenario_number=2,
    )
    scenarios.append(second)
    remove_scenario(scenarios, "2")
    third = build_scenario_record(
        scenarios,
        51.50,
        -3.20,
        50,
        50,
        WEATHER,
        scenario_number=3,
    )
    assert third["label"] == "Proposed Site 3"


def test_weather_failure_does_not_remove_existing_scenarios():
    scenarios = [scenario()]
    with pytest.raises(ValueError, match="Weather unavailable"):
        build_scenario_record(
            scenarios,
            51.48,
            -3.18,
            50,
            50,
            {"error": "Weather unavailable"},
        )
    assert len(scenarios) == 1


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (-91, 0), (0, 181), (0, -181), ("bad", 0), (None, 0)],
)
def test_invalid_global_coordinates_are_rejected(latitude, longitude):
    assert not valid_global_coordinates(latitude, longitude)
    with pytest.raises(ValueError, match="Latitude must be between"):
        build_scenario_record([], latitude, longitude, 50, 50, WEATHER)


def test_outside_cardiff_coordinates_are_flagged_but_remain_valid_globally():
    synthetic_cardiff = box(-3.3, 51.4, -3.0, 51.6)
    assert valid_global_coordinates(51.0, -3.0)
    assert not coordinates_within_cardiff(51.0, -3.0, synthetic_cardiff)
    assert coordinates_within_cardiff(51.5, -3.2, synthetic_cardiff)
    record = scenario(latitude=51.0, longitude=-3.0)
    assert record["latitude"] == 51.0


def test_proposed_marker_popup_contains_scores_risks_and_manual_input_warning():
    item = scenario()
    rendered = build_airis_map([charger_result()], scenarios=[item]).get_root().render()
    for expected in (
        "Proposed Site 1",
        "Current score",
        "Forecast score",
        "Current risk category",
        "Forecast risk category",
        "Manual flood score",
        "Manual deprivation score",
        "manually supplied scenario inputs",
    ):
        assert expected in rendered


def test_comparison_table_values_match_scenario_calculations():
    item = scenario()
    table = scenario_comparison_table([item])
    assert table.iloc[0]["Current score"] == round(item["current_score"], 1)
    assert table.iloc[0]["Forecast score"] == round(item["forecast_score"], 1)
    assert table.iloc[0]["Change"] == round(
        item["forecast_score"] - item["current_score"], 1
    )


def test_proposed_sites_do_not_affect_portfolio_metrics():
    results = [charger_result()]
    before = portfolio_metrics(results)
    temporary_scenarios = [scenario()]
    after = portfolio_metrics(results)
    assert temporary_scenarios
    assert after == before
    assert after["sites_mapped"] == 1


def test_map_component_key_is_stable_and_not_derived_from_selection_or_mode():
    assert MAP_COMPONENT_KEY == "airis_shared_map"


def test_map_renderer_returns_no_interaction_objects(monkeypatch):
    captured = {}

    def fake_st_folium(map_object, **kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(app, "st_folium", fake_st_folium)
    rendered = build_airis_map([charger_result()])
    assert render_airis_map(rendered) == {}
    assert captured["key"] == MAP_COMPONENT_KEY
    assert captured["returned_objects"] == []
    assert captured["use_container_width"] is True
    assert "center" not in captured
    assert "zoom" not in captured
    assert "return_on_hover" not in captured


def test_station_dropdown_id_is_authoritative_selection_input():
    first = charger_result("First", "first")
    second = charger_result("Second", "second")
    assert station_result_by_id([first, second], "second") is second
    assert station_result_by_id([first, second], "missing") is None


def test_ordinary_map_rebuild_uses_default_view_without_fit_bounds():
    rendered = build_airis_map(
        [charger_result()],
        selected_station_id="airis_internal",
    ).get_root().render()
    assert "fitBounds(" not in rendered


def test_selected_site_change_does_not_add_fit_bounds():
    first = charger_result("First", "first")
    second = charger_result("Second", "second")
    rendered = build_airis_map(
        [first, second], selected_station_id="second"
    ).get_root().render()
    assert "fitBounds(" not in rendered
    assert "Second" in rendered


def test_charger_and_proposal_selection_do_not_add_fit_bounds():
    rendered = build_airis_map(
        [charger_result("First", "first"), charger_result("Second", "second")],
        selected_station_id="second",
        scenarios=[scenario()],
    ).get_root().render()
    assert "fitBounds(" not in rendered


def test_fit_bounds_is_only_added_when_explicitly_requested():
    rendered = build_airis_map(
        [charger_result()],
        fit_bounds_locations=[(51.48, -3.18), (51.7, -3.5)],
    ).get_root().render()
    assert "fitBounds(" in rendered


def test_scenario_stores_contributions_and_required_factor_values():
    item = scenario(flood_score=65, deprivation_score=20)
    required = {
        "flood_score",
        "temperature_risk_current",
        "temperature_risk_forecast",
        "deprivation_score",
        "flood_contribution_current",
        "temperature_contribution_current",
        "deprivation_contribution_current",
        "current_overall_score",
        "forecast_overall_score",
    }
    assert required <= item.keys()
    contributions = scenario_current_contributions(item)
    assert sum(contributions.values()) == pytest.approx(
        item["current_overall_score"]
    )


def test_stored_scenario_contribution_data_survive_rerun_and_are_sorted():
    scenarios = [
        scenario(flood_score=10, deprivation_score=60),
        scenario([], flood_score=90, deprivation_score=5),
    ]
    first_values = scenario_current_contributions(scenarios[0])
    persisted = scenarios
    assert scenario_current_contributions(persisted[0]) == first_values
    frame = contribution_dataframe(first_values)
    assert frame["contribution"].tolist() == sorted(
        frame["contribution"].tolist(), reverse=True
    )
    assert frame["factor"].tolist() == [
        factor
        for factor, _ in sorted(
            first_values.items(), key=lambda item: item[1], reverse=True
        )
    ]


def test_removing_one_scenario_preserves_other_contribution_values():
    scenarios = [scenario(), scenario([], flood_score=90, deprivation_score=70)]
    second = scenario_current_contributions(scenarios[1]).copy()
    assert remove_scenario(scenarios, "1")
    assert scenario_current_contributions(scenarios[0]) == second

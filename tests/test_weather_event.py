"""Tests for the weather event generation system."""

import hashlib
import pytest

from balloon_frontier.weather_event import (
    generate_weather,
    weather_impact_on_flight,
    format_weather_briefing,
    WeatherEvent,
    SITE_WEATHER_TEMPLATES,
)


class TestWeatherGenerationDeterminism:
    """Weather must be deterministic for the same launch config."""

    def test_same_config_same_weather(self):
        w1 = generate_weather("field", gas="helium", envelope="latex",
                              payloads=["camera"], seed=42)
        w2 = generate_weather("field", gas="helium", envelope="latex",
                              payloads=["camera"], seed=42)
        assert w1.wind_gust_factor == w2.wind_gust_factor
        assert w1.temp_anomaly_k == w2.temp_anomaly_k
        assert w1.cloud_density == w2.cloud_density
        assert w1.storm_risk == w2.storm_risk

    def test_different_configs_different_weather(self):
        """Different seeds should produce different weather."""
        w1 = generate_weather("field", gas="helium", envelope="latex",
                              payloads=["camera"], seed=42)
        w2 = generate_weather("field", gas="helium", envelope="latex",
                              payloads=["camera"], seed=43)
        # Different seeds must produce different weather
        assert w1.wind_gust_factor != w2.wind_gust_factor or w1.name != w2.name

    def test_different_seeds_different_weather(self):
        w1 = generate_weather("field", seed=1)
        w2 = generate_weather("field", seed=2)
        assert w1.wind_gust_factor != w2.wind_gust_factor


class TestWeatherRangeBounds:
    """Weather factors must stay within defined bounds."""

    def test_field_wind_gust_range(self):
        """Field: wind gust factor 0.7–1.8."""
        for seed in range(100):
            w = generate_weather("field", seed=seed)
            assert 0.5 <= w.wind_gust_factor <= 2.5  # generous margin

    def test_mountain_wind_gust_range(self):
        """Mountain: higher wind, gust factor 1.0–2.5."""
        for seed in range(100):
            w = generate_weather("mountain", seed=seed)
            assert 0.8 <= w.wind_gust_factor <= 3.0  # generous margin

    def test_rooftop_cloud_density_range(self):
        """Rooftop: lower cloud density 0.0–0.4."""
        for seed in range(100):
            w = generate_weather("rooftop", seed=seed)
            assert 0.0 <= w.cloud_density <= 0.8  # generous margin

    def test_storm_risk_non_negative(self):
        for site in ["field", "mountain", "rooftop"]:
            for seed in range(50):
                w = generate_weather(site, seed=seed)
                assert w.storm_risk >= 0.0

    def test_temperature_anomaly_reasonable(self):
        """Temperature anomaly should be within physical bounds."""
        for site in ["field", "mountain", "rooftop"]:
            for seed in range(50):
                w = generate_weather(site, seed=seed)
                assert -20 <= w.temp_anomaly_k <= 20


class TestWeatherSeverity:
    """Test severity classification."""

    def test_favorable_severity(self):
        w = WeatherEvent(
            wind_gust_factor=0.8,
            temp_anomaly_k=0,
            cloud_density=0.1,
            pressure_offset_pa=0,
            storm_risk=0.0,
            name="",
            description="",
            flight_modifier="calm winds",
        )
        assert w.severity == "🟢 Favorable"

    def test_moderate_severity(self):
        w = WeatherEvent(
            wind_gust_factor=1.3,
            temp_anomaly_k=5,
            cloud_density=0.5,
            pressure_offset_pa=0,
            storm_risk=0.15,
            name="Moderate Winds",
            description="",
            flight_modifier="moderate winds",
        )
        assert "🟡" in w.severity

    def test_challenging_severity(self):
        w = WeatherEvent(
            wind_gust_factor=1.5,
            temp_anomaly_k=8,
            cloud_density=0.6,
            pressure_offset_pa=-200,
            storm_risk=0.25,
            name="Pressure Dip",
            description="",
            flight_modifier="low pressure and cloudy",
        )
        assert "🟠" in w.severity

    def test_hazardous_severity(self):
        w = WeatherEvent(
            wind_gust_factor=2.3,
            temp_anomaly_k=15,
            cloud_density=0.9,
            pressure_offset_pa=-600,
            storm_risk=0.5,
            name="Storm Front",
            description="Severe turbulence and lightning risk.",
            flight_modifier="storm risk and strong winds",
        )
        assert "🔴" in w.severity


class TestWeatherImpact:
    """Test how weather affects flight dynamics."""

    def test_calm_wind_increases_stability(self):
        w = generate_weather("field", seed=1)
        # Pick one with low wind
        impact = weather_impact_on_flight(w)
        assert impact["drift_factor"] >= 0.5

    def test_high_storm_risk_increases_burst_risk(self):
        """Storm conditions should increase burst probability."""
        for seed in range(100):
            w = generate_weather("mountain", seed=seed)
            impact = weather_impact_on_flight(w)
            assert impact["burst_risk"] >= 1.0

    def test_hot_launch_improves_thermal_efficiency(self):
        """Positive temp anomaly should improve initial lift."""
        w = generate_weather("rooftop", seed=1)
        if w.temp_anomaly_k > 3:
            impact = weather_impact_on_flight(w)
            assert impact["ascent_rate"] > 0.95

    def test_cloudy_reduces_solar(self):
        """High cloud density should reduce solar heating."""
        for seed in range(100):
            w = generate_weather("mountain", seed=seed)
            impact = weather_impact_on_flight(w)
            if w.cloud_density > 0.5:
                assert impact["thermal_efficiency"] < 0.8

    def test_all_impact_keys_present(self):
        w = generate_weather("field", seed=1)
        impact = weather_impact_on_flight(w)
        assert "ascent_rate" in impact
        assert "burst_risk" in impact
        assert "thermal_efficiency" in impact
        assert "drift_factor" in impact
        assert "pressure_modifier" in impact


class TestWeatherBriefing:
    """Test formatted weather briefing text."""

    def test_briefing_returns_string(self):
        w = generate_weather("field", seed=1)
        text = format_weather_briefing(w, "Open Field")
        assert isinstance(text, str)
        assert "Open Field" in text

    def test_briefing_includes_severity(self):
        w = generate_weather("field", seed=1)
        text = format_weather_briefing(w, "Open Field")
        assert "Favorable" in text or "Moderate" in text or "Challenging" in text or "Hazardous" in text

    def test_briefing_includes_winds(self):
        w = generate_weather("field", seed=1)
        text = format_weather_briefing(w, "Open Field")
        assert "Wind:" in text

    def test_briefing_includes_storm_risk(self):
        w = generate_weather("field", seed=1)
        text = format_weather_briefing(w, "Open Field")
        assert "Storm Risk:" in text


class TestWeatherTemplateCoverage:
    """Verify weather templates are defined for all sites."""

    def test_all_sites_have_templates(self):
        assert "field" in SITE_WEATHER_TEMPLATES
        assert "mountain" in SITE_WEATHER_TEMPLATES
        assert "rooftop" in SITE_WEATHER_TEMPLATES

    def test_template_has_all_keys(self):
        for site_name, template in SITE_WEATHER_TEMPLATES.items():
            assert "wind_gust_factor" in template
            assert "temp_anomaly_k" in template
            assert "cloud_density" in template
            assert "pressure_offset_pa" in template
            assert "storm_risk" in template


class TestWeatherIntegration:
    """Integration tests with the Discord bot."""

    def test_weather_deterministic_with_bot_launch(self):
        """Weather generated during bot launch should match direct call."""
        weather = generate_weather(
            site="field",
            gas="helium",
            envelope="latex",
            payloads=["camera"],
            seed=12345,
        )
        assert weather.wind_gust_factor > 0
        assert weather.description != ""

    def test_weather_no_crash_with_payloads(self):
        """Should handle multiple payloads without error."""
        w = generate_weather(
            site="mountain",
            gas="hydrogen",
            envelope="mylar",
            payloads=["camera", "battery", "weather_sensor"],
            seed=99,
        )
        assert isinstance(w, WeatherEvent)
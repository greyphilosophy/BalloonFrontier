"""Integration tests: progression is a thin rule layer over CATALOG.

Verifies that progression definitions delegate physical/display data to
CATALOG and only own unlock rules (cost, reputation thresholds).
"""

from balloon_frontier.catalog import CATALOG
from balloon_frontier.progression import (
    ENVELOPE_RULES,
    PAYLOAD_RULES,
    SITE_RULES,
    ENVELOPES,
    PAYLOAD_UNLOCKS,
    SITES,
    EnvelopeUnlock,
    PayloadUnlock,
    SiteUnlock,
    PlayerState,
    get_envelope,
    list_unlocked_envelopes,
    list_locked_envelopes,
    list_unlocked_payloads,
    list_locked_payloads,
    list_unlocked_sites,
    list_locked_sites,
)


class TestCatalogIdentity:
    """Compat views should expose the exact catalog definitions."""

    def test_envelope_views_reference_catalog(self):
        for view in ENVELOPES:
            assert view.definition is CATALOG.envelope(view.id)

    def test_payload_views_reference_catalog(self):
        for view in PAYLOAD_UNLOCKS:
            assert view.definition is CATALOG.payload(view.id)

    def test_site_views_reference_catalog(self):
        for view in SITES:
            assert view.definition is CATALOG.site(view.id)


class TestEnvelopeDelegation:
    def test_envelope_names_match_catalog(self):
        for view in ENVELOPES:
            assert view.name == CATALOG.envelope(view.id).name

    def test_envelope_physics_match_catalog(self):
        for view in ENVELOPES:
            definition = CATALOG.envelope(view.id)
            assert view.max_volume_m3 == definition.max_volume_m3
            assert view.mass_kg == definition.mass_kg
            assert view.drag_coefficient == definition.drag_coefficient
            assert view.burst_stretch_ratio == definition.burst_stretch_ratio
            assert view.contained_gas == definition.contained_gas
            assert view.safe_fill_fraction == definition.safe_fill_fraction

    def test_envelope_rules_store_cost_and_reputation(self):
        rule_map = {r.id: r for r in ENVELOPE_RULES}
        assert rule_map["latex"].unlock_cost == 2000
        assert rule_map["latex"].min_reputation == 0
        assert rule_map["mylar"].unlock_cost == 500
        assert rule_map["mylar"].min_reputation == 5
        assert rule_map["blimp"].unlock_cost == 50000
        assert rule_map["blimp"].min_reputation == 20


class TestPayloadDelegation:
    def test_payload_names_match_catalog(self):
        for view in PAYLOAD_UNLOCKS:
            assert view.name == CATALOG.payload(view.id).name

    def test_payload_physics_match_catalog(self):
        for view in PAYLOAD_UNLOCKS:
            definition = CATALOG.payload(view.id)
            assert view.mass_kg == definition.mass_kg
            assert view.has_valve == definition.has_valve

    def test_payload_rules_store_only_unlock_data(self):
        rule_map = {r.id: r for r in PAYLOAD_RULES}
        assert rule_map["flight_computer"].unlock_cost == 750
        assert rule_map["flight_computer"].min_reputation == 3
        assert rule_map["heater"].unlock_cost == 250
        assert rule_map["heater"].min_reputation == 3


class TestSiteDelegation:
    def test_site_names_match_catalog(self):
        for view in SITES:
            assert view.name == CATALOG.site(view.id).name

    def test_site_physics_match_catalog(self):
        for view in SITES:
            definition = CATALOG.site(view.id)
            assert view.altitude_m == definition.altitude_m
            assert view.wind_strength == definition.wind_strength
            assert view.temperature_offset_k == definition.temperature_offset_k

    def test_site_rules_store_reputation_only(self):
        rule_map = {r.id: r for r in SITE_RULES}
        assert rule_map["rooftop"].min_reputation == 3
        assert rule_map["mountain"].min_reputation == 8
        assert all(r.unlock_cost == 0 for r in SITE_RULES)


class TestHelperFunctions:
    """Existing list/get helpers return compat views with catalog plus rules."""

    def test_get_envelope_returns_compat_view(self):
        env = get_envelope("mylar")
        assert isinstance(env, EnvelopeUnlock)
        assert env.id == "mylar"
        assert env.name == "Mylar Party Balloon"
        assert env.name == CATALOG.envelope("mylar").name
        assert env.max_volume_m3 == 200.0
        assert hasattr(env, "burst_stretch_ratio")
        assert hasattr(env, "cost")

    def test_list_unlocked_envelopes_returns_views(self):
        views = list_unlocked_envelopes(0, 0)
        assert "latex" in [v.id for v in views]
        for view in views:
            assert isinstance(view, EnvelopeUnlock)
            assert hasattr(view, "mass_kg")
            assert hasattr(view, "cost")

    def test_list_locked_envelopes_returns_views(self):
        for view in list_locked_envelopes(0, 0):
            assert isinstance(view, EnvelopeUnlock)
            assert hasattr(view, "name")
            assert hasattr(view, "cost")

    def test_list_unlocked_payloads_returns_views(self):
        for view in list_unlocked_payloads(0, 0):
            assert isinstance(view, PayloadUnlock)
            assert hasattr(view, "mass_kg")
            assert hasattr(view, "cost")

    def test_list_locked_payloads_returns_views(self):
        for view in list_locked_payloads(0, 0):
            assert isinstance(view, PayloadUnlock)
            assert hasattr(view, "name")
            assert hasattr(view, "cost")

    def test_list_unlocked_sites_returns_views(self):
        for view in list_unlocked_sites(0, 0):
            assert isinstance(view, SiteUnlock)
            assert hasattr(view, "altitude_m")

    def test_list_locked_sites_returns_views(self):
        for view in list_locked_sites(0, 0):
            assert isinstance(view, SiteUnlock)
            assert hasattr(view, "name")


class TestPlayerStateDelegation:
    def test_default_unlocks_come_from_rules(self):
        player = PlayerState("player")
        assert player.is_envelope_unlocked("latex")
        assert not player.is_envelope_unlocked("mylar")

    def test_unlock_rules_use_or_logic(self):
        player = PlayerState("player")
        player.budget = 500
        assert player.is_envelope_unlocked("mylar")

        other = PlayerState("other")
        other.reputation = 5
        assert other.is_envelope_unlocked("mylar")

    def test_unknown_items_are_not_unlocked(self):
        player = PlayerState("player")
        assert not player.is_envelope_unlocked("missing")
        assert not player.is_payload_unlocked("missing")
        assert not player.is_site_unlocked("missing")

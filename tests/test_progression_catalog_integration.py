"""Balloon Frontier — Progression catalog-integration tests.

After PR #29, progression no longer duplicates catalog data. Progression
stores only unlock rules (cost + reputation thresholds). Every payload,
envelope, and site resolves through CATALOG for names, physics, and display.

These tests verify that the integration is correct and that no ID is lost.
"""
import sys

sys.path.insert(0, "/tmp/BalloonFrontier")

import pytest

from balloon_frontier.catalog import CATALOG
from balloon_frontier.progression import (
    ENVELOPE_RULES,
    ENVELOPES,
    PAYLOAD_RULES,
    PAYLOAD_UNLOCKS,
    SITE_RULES,
    SITES,
    EnvelopeUnlock,
    PayloadUnlock,
    SiteUnlock,
    UnlockableEnvelope,
    UnlockablePayload,
    UnlockableSite,
    get_envelope,
    list_locked_envelopes,
    list_locked_payloads,
    list_locked_sites,
    list_unlocked_envelopes,
    list_unlocked_payloads,
    list_unlocked_sites,
)


class TestRuleIDsMatchCatalog:
    """Every rule ID must resolve in CATALOG."""

    def test_payload_rule_ids_exist_in_catalog(self):
        catalog_ids = {p.id for p in CATALOG.all_payloads()}
        rule_ids = {r.id for r in PAYLOAD_RULES}
        assert rule_ids == catalog_ids, (
            f"Rule/catalog mismatch\n"
            f"  rules-only: {rule_ids - catalog_ids}\n"
            f"  catalog-only: {catalog_ids - rule_ids}"
        )

    def test_envelope_rule_ids_exist_in_catalog(self):
        catalog_ids = {e.id for e in CATALOG.all_envelopes()}
        rule_ids = {r.id for r in ENVELOPE_RULES}
        assert rule_ids == catalog_ids, (
            f"Rule/catalog mismatch\n"
            f"  rules-only: {rule_ids - catalog_ids}\n"
            f"  catalog-only: {catalog_ids - rule_ids}"
        )

    def test_site_rule_ids_exist_in_catalog(self):
        catalog_ids = {s.id for s in CATALOG.all_sites()}
        rule_ids = {r.id for r in SITE_RULES}
        assert rule_ids == catalog_ids, (
            f"Rule/catalog mismatch\n"
            f"  rules-only: {rule_ids - catalog_ids}\n"
            f"  catalog-only: {catalog_ids - rule_ids}"
        )


class TestCompatViews:
    """Backward-compat views must wrap catalog data plus rules."""

    def test_payload_compat_view_has_catalog_properties(self):
        catalog_map = {p.id: p for p in CATALOG.all_payloads()}
        for view in PAYLOAD_UNLOCKS:
            assert isinstance(view, UnlockablePayload)
            cat = catalog_map[view.id]
            assert view.name == cat.name, f"{view.id}: name mismatch"
            assert view.mass_kg == cat.mass_kg, f"{view.id}: mass mismatch"
            assert view.has_valve == cat.has_valve, f"{view.id}: has_valve mismatch"
            assert view.cost == view.rule.unlock_cost
            assert view.min_reputation == view.rule.min_reputation
            assert view.tag == view.rule.category

    def test_envelope_compat_view_has_catalog_properties(self):
        catalog_map = {e.id: e for e in CATALOG.all_envelopes()}
        for view in ENVELOPES:
            assert isinstance(view, EnvelopeUnlock)
            cat = catalog_map[view.id]
            assert view.name == cat.name, f"{view.id}: name mismatch"
            assert view.mass_kg == cat.mass_kg, f"{view.id}: mass mismatch"
            assert view.max_volume_m3 == cat.max_volume_m3, f"{view.id}: volume mismatch"
            assert view.burst_stretch_ratio == cat.burst_stretch_ratio, f"{view.id}: stretch mismatch"
            assert view.contained_gas == cat.contained_gas, f"{view.id}: contained_gas mismatch"
            assert view.cost == view.rule.unlock_cost
            assert view.min_reputation == view.rule.min_reputation

    def test_site_compat_view_has_catalog_properties(self):
        catalog_map = {s.id: s for s in CATALOG.all_sites()}
        for view in SITES:
            assert isinstance(view, SiteUnlock)
            cat = catalog_map[view.id]
            assert view.name == cat.name, f"{view.id}: name mismatch"
            assert view.altitude_m == cat.altitude_m, f"{view.id}: altitude mismatch"
            assert view.wind_strength == cat.wind_strength, f"{view.id}: wind mismatch"
            assert view.cost == view.rule.unlock_cost
            assert view.min_reputation == view.rule.min_reputation


class TestRuleFieldsOnlyInProgression:
    """unlock_cost and min_reputation are progression-specific."""

    def test_payload_rules_store_cost_and_reputation(self):
        rule_map = {r.id: r for r in PAYLOAD_RULES}
        assert rule_map["valve"].unlock_cost == 250
        assert rule_map["valve"].min_reputation == 0
        assert rule_map["heater"].unlock_cost == 250
        assert rule_map["heater"].min_reputation == 3
        assert rule_map["flight_computer"].unlock_cost == 750
        assert rule_map["flight_computer"].min_reputation == 3

    def test_envelope_rules_store_cost_and_reputation(self):
        rule_map = {r.id: r for r in ENVELOPE_RULES}
        assert rule_map["latex"].unlock_cost == 2000
        assert rule_map["latex"].min_reputation == 0
        assert rule_map["mylar"].unlock_cost == 500
        assert rule_map["mylar"].min_reputation == 5
        assert rule_map["blimp"].unlock_cost == 50000
        assert rule_map["blimp"].min_reputation == 20

    def test_site_rules_store_reputation_only(self):
        rule_map = {r.id: r for r in SITE_RULES}
        assert rule_map["rooftop"].min_reputation == 3
        assert rule_map["mountain"].min_reputation == 8
        assert all(r.unlock_cost == 0 for r in SITE_RULES)


class TestHelperFunctions:
    """list_* and get_* return compat views with catalog plus rules."""

    def test_get_envelope_returns_compat_view(self):
        env = get_envelope("mylar")
        assert isinstance(env, EnvelopeUnlock)
        assert env.id == "mylar"
        assert env.name == "Scientific Film Balloon"
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
            assert hasattr(view, "tag")

    def test_list_locked_payloads_returns_views(self):
        views = list_locked_payloads(0, 0)
        ids = [v.id for v in views]
        assert "heater" in ids
        assert "flight_computer" in ids
        assert all(isinstance(view, PayloadUnlock) for view in views)

    def test_list_unlocked_sites_returns_views(self):
        views = list_unlocked_sites(0, 0)
        assert "field" in [v.id for v in views]
        for view in views:
            assert isinstance(view, SiteUnlock)
            assert hasattr(view, "altitude_m")
            assert hasattr(view, "wind_strength")

    def test_list_locked_sites_returns_views(self):
        views = list_locked_sites(0, 0)
        ids = [v.id for v in views]
        assert "rooftop" in ids
        assert "mountain" in ids
        assert all(isinstance(view, SiteUnlock) for view in views)


class TestNoneNotInProgression:
    """'none' is a UI sentinel, not an unlockable item."""

    def test_none_not_in_payload_rules(self):
        assert "none" not in {r.id for r in PAYLOAD_RULES}

    def test_none_not_in_compat_views(self):
        assert "none" not in {p.id for p in PAYLOAD_UNLOCKS}

    def test_catalog_excludes_none_from_all_payloads(self):
        assert "none" not in {p.id for p in CATALOG.all_payloads()}


class TestPlayerSaveFormat:
    """Player progression saves catalog IDs rather than display names."""

    @staticmethod
    def _fully_unlocked_player():
        from balloon_frontier.progression import PlayerState

        player = PlayerState()
        player.budget = 999999
        player.reputation = 999
        player._check_and_apply_unlocks()
        return player

    def test_unlocked_envelopes_contain_only_ids(self):
        catalog_ids = {e.id for e in CATALOG.all_envelopes()}
        player = self._fully_unlocked_player()
        for envelope_id in player.unlocked_envelopes:
            assert envelope_id in catalog_ids, (
                f"unlocked_envelopes contains non-ID: {envelope_id!r}\n"
                f"Expected only catalog IDs: {catalog_ids}"
            )

    def test_unlocked_envelopes_no_display_names(self):
        catalog_names = {e.name for e in CATALOG.all_envelopes()}
        player = self._fully_unlocked_player()
        for envelope_id in player.unlocked_envelopes:
            assert envelope_id not in catalog_names, (
                f"unlocked_envelopes contains display name: {envelope_id!r}\n"
                "This should be an ID (for example, 'mylar'), not a name"
            )

    def test_unlocked_envelopes_count_matches_catalog(self):
        player = self._fully_unlocked_player()
        assert len(player.unlocked_envelopes) == 4, (
            f"Expected 4 IDs, got {len(player.unlocked_envelopes)}: "
            f"{player.unlocked_envelopes}"
        )

    def test_unlocked_payloads_contain_only_ids(self):
        catalog_ids = {p.id for p in CATALOG.all_payloads() if p.id != "none"}
        player = self._fully_unlocked_player()
        for payload_id in player.unlocked_payloads:
            assert payload_id in catalog_ids, (
                f"unlocked_payloads contains non-ID: {payload_id!r}"
            )

    def test_unlocked_sites_contain_only_ids(self):
        catalog_ids = {s.id for s in CATALOG.all_sites()}
        player = self._fully_unlocked_player()
        for site_id in player.unlocked_sites:
            assert site_id in catalog_ids, (
                f"unlocked_sites contains non-ID: {site_id!r}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

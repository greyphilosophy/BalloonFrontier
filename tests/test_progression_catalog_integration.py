"""Balloon Frontier — Progression catalog-integration tests.

After PR #29, progression no longer duplicates catalog data.  Progression
stores only unlock rules (cost + reputation thresholds).  Every payload,
envelope, and site resolves through CATALOG for names, physics, and display.

These tests verify that the integration is correct and that no ID is lost.
"""
import sys
sys.path.insert(0, "/tmp/BalloonFrontier")

import pytest
from balloon_frontier.catalog import CATALOG
from balloon_frontier.progression import (
    PAYLOAD_RULES, ENVELOPE_RULES, SITE_RULES,
    PAYLOAD_UNLOCKS, ENVELOPES, SITES,
    PayloadUnlock, EnvelopeUnlock, SiteUnlock,
    UnlockablePayload, UnlockableEnvelope, UnlockableSite,
    list_unlocked_payloads, list_locked_payloads,
    list_unlocked_envelopes, list_locked_envelopes,
    list_unlocked_sites, list_locked_sites,
    get_envelope,
)


# ═══════════════════════════════════════════════════════════════════════════
# Rule-to-catalog ID alignment
# ═══════════════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════════════
# Compat views resolve through catalog
# ═══════════════════════════════════════════════════════════════════════════


class TestCompatViews:
    """Backward-compat views must wrap catalog data + rules."""

    def test_payload_compat_view_has_catalog_properties(self):
        """UnlockablePayload delegates name/mass/has_valve to catalog."""
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
        """UnlockableEnvelope delegates name/mass/volume/stretch to catalog."""
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
        """UnlockableSite delegates name/altitude/wind to catalog."""
        catalog_map = {s.id: s for s in CATALOG.all_sites()}
        for view in SITES:
            assert isinstance(view, SiteUnlock)
            cat = catalog_map[view.id]
            assert view.name == cat.name, f"{view.id}: name mismatch"
            assert view.altitude_m == cat.altitude_m, f"{view.id}: altitude mismatch"
            assert view.wind_strength == cat.wind_strength, f"{view.id}: wind mismatch"
            assert view.cost == view.rule.unlock_cost
            assert view.min_reputation == view.rule.min_reputation


# ═══════════════════════════════════════════════════════════════════════════
# Rule-only fields (progression stores these, catalog does not)
# ═══════════════════════════════════════════════════════════════════════════


class TestRuleFieldsOnlyInProgression:
    """unlock_cost and min_reputation are progression-specific."""

    def test_payload_rules_store_cost_and_reputation(self):
        rule_map = {r.id: r for r in PAYLOAD_RULES}
        # valve: cost=250, rep=0
        v = rule_map["valve"]
        assert v.unlock_cost == 250
        assert v.min_reputation == 0
        # heater: cost=250, rep=3
        h = rule_map["heater"]
        assert h.unlock_cost == 250
        assert h.min_reputation == 3
        # flight_computer: cost=750, rep=3
        fc = rule_map["flight_computer"]
        assert fc.unlock_cost == 750
        assert fc.min_reputation == 3

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
        # No sites have unlock_cost > 0
        for r in SITE_RULES:
            assert r.unlock_cost == 0


# ═══════════════════════════════════════════════════════════════════════════
# Helper functions return compat views (backward compatible)
# ═══════════════════════════════════════════════════════════════════════════


class TestHelperFunctions:
    """list_* and get_* return compat views with catalog + rule."""

    def test_get_envelope_returns_compat_view(self):
        env = get_envelope("mylar")
        assert isinstance(env, EnvelopeUnlock)
        assert env.id == "mylar"
        assert env.name == "Mylar Party Balloon"
        assert hasattr(env, "burst_stretch_ratio")  # from catalog
        assert hasattr(env, "cost")  # from rule

    def test_list_unlocked_envelopes_returns_views(self):
        views = list_unlocked_envelopes(0, 0)
        ids = [v.id for v in views]
        assert "latex" in ids  # always unlocked
        for v in views:
            assert isinstance(v, EnvelopeUnlock)
            assert hasattr(v, "mass_kg")
            assert hasattr(v, "cost")

    def test_list_locked_envelopes_returns_views(self):
        views = list_locked_envelopes(0, 0)
        for v in views:
            assert isinstance(v, EnvelopeUnlock)
            assert hasattr(v, "name")
            assert hasattr(v, "cost")

    def test_list_unlocked_payloads_returns_views(self):
        views = list_unlocked_payloads(0, 0)
        ids = [v.id for v in views]
        # All payloads with cost=0 and rep=0 should be unlocked
        for view in views:
            assert isinstance(view, PayloadUnlock)
            assert hasattr(view, "mass_kg")
            assert hasattr(view, "cost")
            assert hasattr(view, "tag")

    def test_list_locked_payloads_returns_views(self):
        views = list_locked_payloads(0, 0)
        ids = [v.id for v in views]
        # heater and flight_computer require rep>=3
        assert "heater" in ids
        assert "flight_computer" in ids
        for view in views:
            assert isinstance(view, PayloadUnlock)

    def test_list_unlocked_sites_returns_views(self):
        views = list_unlocked_sites(0, 0)
        ids = [v.id for v in views]
        assert "field" in ids  # always unlocked
        for v in views:
            assert isinstance(v, SiteUnlock)
            assert hasattr(v, "altitude_m")
            assert hasattr(v, "wind_strength")

    def test_list_locked_sites_returns_views(self):
        views = list_locked_sites(0, 0)
        ids = [v.id for v in views]
        assert "rooftop" in ids
        assert "mountain" in ids
        for v in views:
            assert isinstance(v, SiteUnlock)


# ═══════════════════════════════════════════════════════════════════════════
# "none" must NOT appear anywhere in progression
# ═══════════════════════════════════════════════════════════════════════════


class TestNoneNotInProgression:
    """'none' is a UI sentinel, not an unlockable item."""

    def test_none_not_in_payload_rules(self):
        ids = {r.id for r in PAYLOAD_RULES}
        assert "none" not in ids

    def test_none_not_in_compat_views(self):
        ids = {p.id for p in PAYLOAD_UNLOCKS}
        assert "none" not in ids

    def test_catalog_excludes_none_from_all_payloads(self):
        ids = {p.id for p in CATALOG.all_payloads()}
        assert "none" not in ids


# ═══════════════════════════════════════════════════════════════════════════
# Player save format — IDs only, no display names
# ═══════════════════════════════════════════════════════════════════════════


class TestPlayerSaveFormat:
    """unlocked_envelopes/payloads/sites must contain only catalog IDs.

    Display names are derived from CATALOG at runtime for display.
    Storing names in save data causes stale references when catalog items
    are renamed and inflates save size.
    """

    def test_unlocked_envelopes_contain_only_ids(self):
        """After _check_and_apply_unlocks(), every value in unlocked_envelopes
        must be a valid catalog envelope ID — never a display name."""
        from balloon_frontier.progression import PlayerState

        catalog_ids = {e.id for e in CATALOG.all_envelopes()}

        player = PlayerState()
        # Trigger all unlocks by giving enough budget
        player.budget = 999999
        player.reputation = 999
        new_unlocks = player._check_and_apply_unlocks()

        for envelope_id in player.unlocked_envelopes:
            assert envelope_id in catalog_ids, (
                f"unlocked_envelopes contains non-ID: {envelope_id!r}\n"
                f"Expected only catalog IDs: {catalog_ids}"
            )

    def test_unlocked_envelopes_no_display_names(self):
        """No display name should appear in unlocked_envelopes."""
        from balloon_frontier.progression import PlayerState

        catalog_names = {e.name for e in CATALOG.all_envelopes()}

        player = PlayerState()
        player.budget = 999999
        player.reputation = 999
        player._check_and_apply_unlocks()

        for envelope_id in player.unlocked_envelopes:
            assert envelope_id not in catalog_names, (
                f"unlocked_envelopes contains display name: {envelope_id!r}\n"
                f"This should be an ID (e.g. 'mylar'), not a name"
            )

    def test_unlocked_envelopes_count_matches_catalog(self):
        """Each unlocked envelope should add exactly one ID, not two."""
        from balloon_frontier.progression import PlayerState

        player = PlayerState()
        player.budget = 999999
        player.reputation = 999
        player._check_and_apply_unlocks()

        # All 4 envelopes should be unlocked
        assert len(player.unlocked_envelopes) == 4, (
            f"Expected 4 IDs, got {len(player.unlocked_envelopes)}: {player.unlocked_envelopes}"
        )

    def test_unlocked_payloads_contain_only_ids(self):
        """Payloads follow the same rule: IDs only."""
        from balloon_frontier.progression import PlayerState

        catalog_ids = {p.id for p in CATALOG.all_payloads() if p.id != "none"}

        player = PlayerState()
        player.budget = 999999
        player.reputation = 999
        player._check_and_apply_unlocks()

        for payload_id in player.unlocked_payloads:
            assert payload_id in catalog_ids, (
                f"unlocked_payloads contains non-ID: {payload_id!r}"
            )

    def test_unlocked_sites_contain_only_ids(self):
        """Sites follow the same rule: IDs only."""
        from balloon_frontier.progression import PlayerState

        catalog_ids = {s.id for s in CATALOG.all_sites()}

        player = PlayerState()
        player.reputation = 999
        player._check_and_apply_unlocks()

        for site_id in player.unlocked_sites:
            assert site_id in catalog_ids, (
                f"unlocked_sites contains non-ID: {site_id!r}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
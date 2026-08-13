"""Result rendering should respect mission-local launch-site labels."""

from balloon_frontier.career_prologue import first_flight_site_info
from balloon_frontier.discord_ui.configurator import _Step
from balloon_frontier.discord_ui.launch_handler import _site_info_for_configurator


class _FirstFlightConfigurator:
    def _first_flight_options(self, step):
        assert step == _Step.CHOOSE_SITE
        return {"field": first_flight_site_info()}


class _PlainConfigurator:
    pass


def test_first_flight_results_use_school_athletic_field_label():
    site = _site_info_for_configurator(_FirstFlightConfigurator(), "field")
    assert site.name == "School Athletic Field"


def test_other_modes_keep_global_open_field_label():
    site = _site_info_for_configurator(_PlainConfigurator(), "field")
    assert site.name == "Open Field"

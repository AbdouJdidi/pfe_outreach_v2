from dataclasses import replace

from src import config


def test_bad_env_values_are_reported(capsys):
    """A score threshold outside 0-100 (e.g. a typo like 500) must be caught, loudly."""
    config._sanity_check(replace(config.settings, min_outreach_score=500))
    assert "MIN_OUTREACH_SCORE=500" in capsys.readouterr().out


def test_reversed_delay_range_is_reported(capsys):
    config._sanity_check(replace(config.settings, send_delay_min=60, send_delay_max=19))
    assert "SEND_DELAY_MAX" in capsys.readouterr().out


def test_healthy_settings_print_nothing(capsys):
    config._sanity_check(replace(config.settings, min_outreach_score=50, send_delay_min=60, send_delay_max=180))
    assert capsys.readouterr().out == ""

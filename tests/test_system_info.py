"""
System info server.

These are the tools that reported success: False on every call, or reported
success while returning nothing, so the assertions are about real values
rather than about the shape of the response.
"""

import json
import os

import pytest

READ_ONLY_TOOLS = [
    "get_os_info",
    "get_cpu_info",
    "get_memory_info",
    "get_disk_info",
    "get_network_info",
    "get_processes",
    "get_uptime",
    "get_load_average",
    "get_sensors",
    "get_platform_info",
    "get_timezone",
    "get_env_variables",
    "get_full_status",
]


@pytest.mark.parametrize("tool_name", READ_ONLY_TOOLS)
def test_tool_succeeds(system_info, tool_name):
    result = getattr(system_info, tool_name)()
    assert result["success"], f"{tool_name} failed: {result.get('error')}"


@pytest.mark.parametrize("tool_name", READ_ONLY_TOOLS)
def test_tool_output_is_json_serializable(system_info, tool_name):
    """
    MCP responses cross a JSON boundary. A namedtuple or Path in the payload
    fails at the transport, not in the tool, so it is easy to miss locally.
    """
    json.dumps(getattr(system_info, tool_name)())


def test_disk_info_reports_real_usage(system_info):
    """Regression: read .total off disk_partitions(), which does not have it."""
    result = system_info.get_disk_info()

    assert result["disks"], "no partitions reported"
    usable = [d for d in result["disks"] if "total" in d]
    assert usable, "every partition failed to report usage"
    assert usable[0]["total"] > 0
    assert 0 <= usable[0]["percent"] <= 100


def test_network_info_reports_interfaces(system_info):
    """Regression: subscripted str keys from net_if_stats(); always failed."""
    result = system_info.get_network_info()

    assert result["interfaces"], "no interfaces reported"
    names = [i["name"] for i in result["interfaces"]]
    assert any(n.lower().startswith(("lo", "en", "eth")) for n in names), names

    # Windows names its loopback "Loopback Pseudo-Interface 1"; macOS/Linux
    # use "lo0"/"lo". Match case-insensitively rather than assuming "lo".
    loopback = next(
        i for i in result["interfaces"] if i["name"].lower().startswith("lo")
    )
    assert loopback["addresses"], "loopback reported no addresses"
    assert loopback["status"] in ("up", "down")


def test_sensors_does_not_fake_an_empty_reading(system_info):
    """
    Regression: a TypeError was swallowed into thermal: [], so an unreadable
    sensor and a machine with no sensors looked identical. The tool must now
    say which case it is.
    """
    sensors = system_info.get_sensors()["sensors"]

    assert "thermal_supported" in sensors
    if sensors["thermal_supported"] and sensors["thermal"]:
        assert sensors["thermal"][0]["current"] is not None


def test_uptime_is_elapsed_time_not_remainder_of_day(system_info):
    """Regression: used .seconds, which wraps every 24h, not total_seconds()."""
    result = system_info.get_uptime()

    assert result["uptime_seconds"] > 0
    assert isinstance(result["uptime_seconds"], float)


def test_timezone_works_without_dst_rules(system_info):
    """
    Regression: called .total_seconds() on dst(), which is None for the
    fixed-offset tzinfo astimezone() attaches — so it failed on every
    machine, including every CI runner (which run in UTC).
    """
    result = system_info.get_timezone()

    assert result["success"], result.get("error")
    assert isinstance(result["utc_offset"], float)
    assert isinstance(result["dst"], bool)


def test_cpu_reports_one_entry_per_core(system_info):
    result = system_info.get_cpu_info()
    assert len(result["cores"]) == result["cpu_count"]
    assert all(0 <= c["percent"] <= 100 for c in result["cores"])


def test_memory_totals_are_consistent(system_info):
    result = system_info.get_memory_info()
    assert result["total"] > 0
    assert result["used"] <= result["total"]


def test_process_info_for_this_process(system_info):
    result = system_info.get_process_info(os.getpid())
    assert result["success"]
    assert result["pid"] == os.getpid()


def test_env_variables_are_redacted(system_info):
    """
    The security pass redacts secret-looking names. This asserts the
    redaction actually fires, rather than trusting that it was wired up.
    """
    os.environ["TEST_FAKE_API_KEY"] = "super-secret-value"
    try:
        result = system_info.get_env_variables()
        assert "super-secret-value" not in json.dumps(result)
    finally:
        del os.environ["TEST_FAKE_API_KEY"]

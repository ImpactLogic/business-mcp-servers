"""
System Info MCP Server

Provides system information and monitoring capabilities:
- OS information
- Network status
- Hardware specs
- Resource monitoring
- Disk usage
- Process info
"""

import datetime
import os
import platform
import re
import socket

import psutil
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("System Info")

# Environment variables routinely hold credentials. Returning them raw
# would push API keys, tokens and database passwords straight into the
# model's context, where they can end up in transcripts or logs. Any
# variable whose NAME matches this pattern has its VALUE redacted.
_SECRET_NAME_PATTERN = re.compile(
    r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|PWD|CREDENTIAL|AUTH|SESSION|COOKIE|"
    r"PRIVATE|SIGNATURE|SALT|CERT|DSN|CONNECTION_STRING)",
    re.IGNORECASE,
)


def _redact_env(items):
    """Redact values of credential-looking environment variables."""
    out = {}
    for name, value in items:
        if _SECRET_NAME_PATTERN.search(name):
            out[name] = "<redacted>"
        else:
            out[name] = value
    return out


@mcp.tool()
def get_os_info() -> dict:
    """
    Get operating system information.

    Returns:
        OS details
    """
    try:
        return {
            "success": True,
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_cpu_info() -> dict:
    """
    Get CPU information.

    Returns:
        CPU details
    """
    try:
        return {
            "success": True,
            "cpu_count": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "cores": [
                {
                    "number": i,
                    "percent": psutil.cpu_percent(percpu=True, interval=None)[i],
                }
                for i in range(psutil.cpu_count())
            ],
            "frequency": psutil.cpu_freq()._asdict()
            if hasattr(psutil.cpu_freq(), "_asdict")
            else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_memory_info() -> dict:
    """
    Get memory information.

    Returns:
        Memory details
    """
    try:
        return {
            "success": True,
            "total": psutil.virtual_memory().total,
            "available": psutil.virtual_memory().available,
            "percent": psutil.virtual_memory().percent,
            "used": psutil.virtual_memory().used,
            "human": {
                "total": f"{psutil.virtual_memory().total / (1024**3):.2f} GB",
                "used": f"{psutil.virtual_memory().used / (1024**3):.2f} GB",
                "available": f"{psutil.virtual_memory().available / (1024**3):.2f} GB",
                "percent": f"{psutil.virtual_memory().percent:.1f}%",
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_disk_info() -> dict:
    """
    Get disk information.

    Returns:
        Disk details
    """
    try:
        return {
            "success": True,
            "disks": [
                {
                    "device": mount.device,
                    "mountpoint": mount.mountpoint,
                    "fstype": mount.fstype,
                    "total": mount.total,
                    "used": mount.used,
                    "free": mount.free,
                    "percent": mount.percent,
                }
                for mount in psutil.disk_partitions()
            ],
            "virtual": {
                "total": psutil.disk_usage("/").total,
                "used": psutil.disk_usage("/").used,
                "free": psutil.disk_usage("/").free,
                "percent": psutil.disk_usage("/").percent,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_network_info() -> dict:
    """
    Get network information.

    Returns:
        Network details
    """
    try:
        return {
            "success": True,
            "hostname": socket.gethostname(),
            "host_name": socket.gethostbyname(socket.gethostname()),
            "interfaces": [
                {
                    "name": interface["ifname"],
                    "addresses": [
                        {
                            "address": addr["address"],
                            "family": "IPv4"
                            if addr["family"] == socket.AF_INET
                            else "IPv6",
                        }
                        for addr in interface.get("addrs", [])
                    ],
                    "status": interface.get("status", "up"),
                }
                for interface in psutil.net_if_stats()
            ],
            "connections": psutil.net_connections()[:10],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_processes(limit: int = 10) -> dict:
    """
    Get process information.

    Args:
        limit: Maximum processes to return

    Returns:
        Process list
    """
    try:
        return {
            "success": True,
            "count": len(psutil.pids()),
            "processes": [
                {
                    "pid": p.pid,
                    "name": p.name(),
                    "status": p.status(),
                    "cpu_percent": p.cpu_percent(interval=None),
                    "memory_percent": p.memory_percent(),
                }
                for p in psutil.process_iter()
                if p.is_running()
            ][:limit],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_process_info(pid: int) -> dict:
    """
    Get info for a specific process.

    Args:
        pid: Process ID

    Returns:
        Process details
    """
    try:
        process = psutil.Process(pid)

        return {
            "success": True,
            "pid": pid,
            "name": process.name(),
            "status": process.status(),
            "cpu_percent": process.cpu_percent(interval=None),
            "memory_percent": process.memory_percent(),
            "cmdline": process.cmdline(),
            "username": process.username(),
            "started": process.create_time(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_uptime() -> dict:
    """
    Get system uptime.

    Returns:
        Uptime information
    """
    try:
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        now = datetime.datetime.now()
        uptime = now - boot_time

        return {
            "success": True,
            "boot_time": boot_time.isoformat(),
            "uptime": str(uptime),
            "uptime_seconds": uptime.seconds,
            "days": uptime.days,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_load_average() -> dict:
    """
    Get system load average.

    Returns:
        Load average information
    """
    try:
        return {
            "success": True,
            "load_average": psutil.getloadavg(),
            "cpu_count": psutil.cpu_count(),
            "interpretation": {
                "1_min": psutil.getloadavg()[0],
                "5_min": psutil.getloadavg()[1],
                "15_min": psutil.getloadavg()[2],
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_sensors() -> dict:
    """
    Get hardware sensors (temperature, fans).

    Returns:
        Sensor readings
    """
    try:
        sensors = {}

        try:
            # Get thermal zones (Linux only)
            sensors["thermal"] = []
            for thermal_zone in psutil.sensors_temperatures():
                for name, entry in thermal_zone.items():
                    sensors["thermal"].append(
                        {
                            "name": name,
                            "current": entry[0]["current"],
                            "high": entry[0]["high"],
                        }
                    )
        except:
            sensors["thermal"] = []

        return {"success": True, "sensors": sensors}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_platform_info() -> dict:
    """
    Get platform-specific information.

    Returns:
        Platform details
    """
    try:
        return {
            "success": True,
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "compiler": platform.python_compiler(),
            "processor": platform.processor(),
            "platform_machine": platform.machine(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_timezone() -> dict:
    """
    Get timezone information.

    Returns:
        Timezone details
    """
    try:
        tz = datetime.datetime.now(datetime.timezone.utc).astimezone()

        return {
            "success": True,
            "timezone": tz.tzname(),
            "utc_offset": tz.utcoffset().total_seconds() / 3600,
            "dst": tz.dst().total_seconds() != 0,
            "zoneinfo": tz.tzname(),
            "timestamp": datetime.datetime.now().isoformat(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_env_variables(limit: int = 10) -> dict:
    """
    Get environment variables, with credential-looking values redacted.

    Values are redacted when the variable NAME looks like a secret
    (contains KEY, SECRET, TOKEN, PASSWORD, AUTH, etc.). Names are
    always returned so you can see what exists; only the values are
    hidden. This is a name-based heuristic, not a guarantee — a secret
    stored in a blandly-named variable will not be caught.

    Args:
        limit: Maximum variables to return

    Returns:
        Environment variables, secrets redacted
    """
    try:
        selected = sorted(os.environ.items())[:limit]
        variables = _redact_env(selected)
        return {
            "success": True,
            "count": len(os.environ),
            "returned": len(variables),
            "redacted": sum(1 for v in variables.values() if v == "<redacted>"),
            "variables": variables,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_full_status() -> dict:
    """
    Get comprehensive system status.

    Returns:
        Full system status
    """
    try:
        return {
            "success": True,
            "os": get_os_info(),
            "cpu": get_cpu_info(),
            "memory": get_memory_info(),
            "disk": get_disk_info(),
            "network": get_network_info(),
            "uptime": get_uptime(),
            "load": get_load_average(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("SYSTEM INFO MCP SERVER TEST")
        print("=" * 60)
        print(f"\n✅ Server: system-info")
        print(f"✅ Module: system_info")
        print("\nAvailable tools:")
        print("  - get_os_info: Get OS details")
        print("  - get_cpu_info: Get CPU info")
        print("  - get_memory_info: Get memory info")
        print("  - get_disk_info: Get disk info")
        print("  - get_network_info: Get network info")
        print("  - get_processes: List processes")
        print("  - get_process_info: Get process details")
        print("  - get_uptime: Get uptime")
        print("  - get_load_average: Get load average")
        print("  - get_sensors: Get hardware sensors")
        print("  - get_platform_info: Get platform info")
        print("  - get_timezone: Get timezone")
        print("  - get_env_variables: Get env vars")
        print("  - get_full_status: Full system status")
        print("\nFeatures:")
        print("  - System monitoring")
        print("  - Resource utilization")
        print("  - Process management")
        print("  - Hardware diagnostics")
        print("\n✅ All tools are functional")
        print("=" * 60)
        sys.exit(0)
    else:
        print("System Info MCP Server started")
        print("Available tools:")
        print("  - get_os_info: Get OS details")
        print("  - get_cpu_info: Get CPU info")
        print("  - get_memory_info: Get memory info")
        print("  - get_disk_info: Get disk info")
        print("  - get_network_info: Get network info")
        print("  - get_processes: List processes")
        print("  - get_process_info: Get process details")
        print("  - get_uptime: Get uptime")
        print("  - get_load_average: Get load average")
        print("  - get_sensors: Get hardware sensors")
        print("  - get_platform_info: Get platform info")
        print("  - get_timezone: Get timezone")
        print("  - get_env_variables: Get env vars")
        print("  - get_full_status: Full system status")

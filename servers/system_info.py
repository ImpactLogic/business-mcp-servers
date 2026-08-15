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
import time

import psutil
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("System Info")

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
        # Sample percpu once and reuse: calling cpu_percent() per core meant
        # N full samples per request, and cpu_freq() was called twice.
        per_core = psutil.cpu_percent(percpu=True, interval=None)
        # cpu_freq() doesn't exist on every platform (some macOS runners,
        # containers without the sysfs it reads on Linux); hasattr guards
        # the attribute, and it can also legitimately return None.
        freq = psutil.cpu_freq() if hasattr(psutil, "cpu_freq") else None

        return {
            "success": True,
            "cpu_count": psutil.cpu_count(),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "cores": [
                {"number": i, "percent": percent} for i, percent in enumerate(per_core)
            ],
            "frequency": freq._asdict() if freq else None,
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
        # disk_partitions() yields sdiskpart(device, mountpoint, fstype, opts)
        # — it carries no usage figures. Usage comes from disk_usage() per
        # mountpoint, which can fail on unreadable or disconnected mounts.
        disks = []
        for mount in psutil.disk_partitions():
            entry = {
                "device": mount.device,
                "mountpoint": mount.mountpoint,
                "fstype": mount.fstype,
            }
            try:
                usage = psutil.disk_usage(mount.mountpoint)
                entry.update(
                    total=usage.total,
                    used=usage.used,
                    free=usage.free,
                    percent=usage.percent,
                )
            except (PermissionError, OSError) as e:
                entry["error"] = str(e)
            disks.append(entry)

        return {
            "success": True,
            "disks": disks,
            "virtual": {
                "total": psutil.disk_usage("/").total,
                "used": psutil.disk_usage("/").used,
                "free": psutil.disk_usage("/").free,
                "percent": psutil.disk_usage("/").percent,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _address_family(family) -> str:
    """Human-readable name for a socket address family."""
    if family == socket.AF_INET:
        return "IPv4"
    if family == socket.AF_INET6:
        return "IPv6"
    if hasattr(psutil, "AF_LINK") and family == psutil.AF_LINK:
        return "MAC"
    return str(family)


@mcp.tool()
def get_network_info() -> dict:
    """
    Get network information.

    Returns:
        Network details
    """
    try:
        hostname = socket.gethostname()
        try:
            host_ip = socket.gethostbyname(hostname)
        except OSError:
            host_ip = None

        # net_if_addrs()/net_if_stats() are dicts keyed by interface name.
        # Iterating one yields str keys, so the addresses have to be joined
        # from net_if_addrs() rather than subscripted off the stats entry.
        stats = psutil.net_if_stats()
        interfaces = []
        for name, addrs in psutil.net_if_addrs().items():
            stat = stats.get(name)
            interfaces.append(
                {
                    "name": name,
                    "addresses": [
                        {
                            "address": addr.address,
                            "family": _address_family(addr.family),
                            "netmask": addr.netmask,
                        }
                        for addr in addrs
                    ],
                    "status": "up" if stat and stat.isup else "down",
                    "speed_mbps": stat.speed if stat else None,
                }
            )

        # net_connections() yields namedtuples, which are not JSON
        # serializable, and needs elevated privileges on macOS.
        try:
            connections = [c._asdict() for c in psutil.net_connections()[:10]]
            for conn in connections:
                conn["laddr"] = tuple(conn["laddr"]) or None
                conn["raddr"] = tuple(conn["raddr"]) or None
        except (psutil.AccessDenied, PermissionError):
            connections = None

        return {
            "success": True,
            "hostname": hostname,
            "host_name": host_ip,
            "interfaces": interfaces,
            "connections": connections,
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
        processes = []
        for p in psutil.process_iter():
            if len(processes) >= limit:
                break
            try:
                if not p.is_running():
                    continue
                processes.append(
                    {
                        "pid": p.pid,
                        "name": p.name(),
                        "status": p.status(),
                        "cpu_percent": p.cpu_percent(interval=None),
                        "memory_percent": p.memory_percent(),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # A single protected process (e.g. macOS's pid-0
                # kernel_task) must not take down the whole listing.
                continue

        return {"success": True, "count": len(psutil.pids()), "processes": processes}
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
            # total_seconds(), not .seconds — the latter is the remainder
            # after whole days, so it wrapped to ~0 once a day.
            "uptime_seconds": uptime.total_seconds(),
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

        # sensors_temperatures() returns {chip_name: [shwtemp, ...]}, so it
        # must be walked with .items() — iterating it yields str keys, and
        # the resulting TypeError used to be swallowed into an empty list.
        # It is absent entirely on macOS and Windows, which is reported as
        # `supported: False` rather than as an empty reading.
        if hasattr(psutil, "sensors_temperatures"):
            thermal = []
            for chip, entries in psutil.sensors_temperatures().items():
                for entry in entries:
                    thermal.append(
                        {
                            "chip": chip,
                            "label": entry.label or chip,
                            "current": entry.current,
                            "high": entry.high,
                            "critical": entry.critical,
                        }
                    )
            sensors["thermal"] = thermal
            sensors["thermal_supported"] = True
        else:
            sensors["thermal"] = []
            sensors["thermal_supported"] = False

        if hasattr(psutil, "sensors_fans"):
            sensors["fans"] = [
                {"chip": chip, "label": entry.label or chip, "rpm": entry.current}
                for chip, entries in psutil.sensors_fans().items()
                for entry in entries
            ]
        else:
            sensors["fans"] = []

        battery = getattr(psutil, "sensors_battery", lambda: None)()
        sensors["battery"] = battery._asdict() if battery else None

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

        # astimezone() with no argument attaches a *fixed-offset* tzinfo, so
        # its .dst() is always None — it cannot answer the DST question at
        # all. Calling .total_seconds() on it unguarded used to raise, which
        # made this tool fail on every machine. time.localtime().tm_isdst is
        # the platform's real answer, so use that instead.
        offset = tz.utcoffset()
        is_dst = time.localtime().tm_isdst

        return {
            "success": True,
            "timezone": tz.tzname(),
            "utc_offset": offset.total_seconds() / 3600 if offset else 0.0,
            "dst": is_dst > 0,
            "dst_known": is_dst >= 0,
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
    mcp.run()

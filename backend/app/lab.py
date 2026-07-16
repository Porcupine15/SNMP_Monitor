"""Deterministic simulated equipment for UI development and API tests."""

from copy import deepcopy

LAB_PROFILES = {
    "access-switch": {
        "name": "LAB-SW-24G",
        "type": "switch",
        "ports": [
            {"port": 1, "description": "Workstation-01", "status": "up", "mode": "Access", "speed": "1000 Mbps", "pvid": 10, "mac_count": 1, "macs": ["00:11:22:33:44:01"], "ips": ["192.168.10.21"]},
            {"port": 2, "description": "Wi-Fi AP", "status": "up", "mode": "Trunk", "speed": "1000 Mbps", "pvid": 1, "mac_count": 4, "macs": ["00:11:22:33:44:02", "00:11:22:33:44:03", "00:11:22:33:44:04", "00:11:22:33:44:05"], "ips": ["192.168.0.20", "192.168.10.32"]},
            {"port": 3, "description": "Printer", "status": "up", "mode": "Access", "speed": "100 Mbps", "pvid": 20, "mac_count": 1, "macs": ["00:11:22:33:44:10"], "ips": ["192.168.20.15"]},
            {"port": 4, "description": "", "status": "down", "mode": "Access", "speed": "", "pvid": 10, "mac_count": 0, "macs": [], "ips": []},
        ],
    },
    "office-printer": {
        "name": "LAB-PRN-01",
        "type": "printer",
        "toner": {"black": 61, "cyan": 48, "magenta": 48, "yellow": 48},
        "status": "online",
    },
    "mikrotik-router": {
        "name": "LAB-MT-01", "type": "router", "status": "online",
        "interfaces": [{"name": "ether1-WAN", "status": "up", "speed": "1000 Mbps"}, {"name": "bridge-LAN", "status": "up", "speed": "1000 Mbps"}],
        "arp": [{"ip": "192.168.88.10", "mac": "08:00:27:aa:bb:01"}, {"ip": "192.168.88.20", "mac": "08:00:27:aa:bb:02"}],
    },
    "poe-switch": {
        "name": "LAB-POE-08", "type": "switch", "status": "online",
        "ports": [{"port": 1, "description": "IP Camera", "status": "up", "mode": "Access", "speed": "100 Mbps", "pvid": 30, "mac_count": 1, "macs": ["00:ca:fe:00:00:01"], "ips": ["192.168.30.11"], "poe": "7.2 W"}],
    },
}


def list_profiles() -> list[dict]:
    return [{"id": profile_id, "name": data["name"], "type": data["type"]} for profile_id, data in LAB_PROFILES.items()]


def get_profile(profile_id: str) -> dict | None:
    data = LAB_PROFILES.get(profile_id)
    return deepcopy(data) if data else None

import ipaddress, socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.snmp_client import ping_device

def arp_table() -> dict[str, str]:
    entries = {}
    try:
        with open('/proc/net/arp', encoding='utf-8') as file:
            next(file)
            for line in file:
                parts = line.split()
                if len(parts) >= 4 and parts[3] != '00:00:00:00:00:00': entries[parts[0]] = parts[3].lower()
    except OSError: pass
    return entries

def scan(network: str, timeout: float = 1) -> list[dict]:
    hosts = list(ipaddress.ip_network(network, strict=False).hosts())
    with ThreadPoolExecutor(max_workers=min(32, len(hosts) or 1)) as pool:
        future_ips = {pool.submit(ping_device, str(ip), timeout): str(ip) for ip in hosts}
        alive = [ip for future, ip in future_ips.items() if future.result()]
    arps = arp_table(); result = []
    for ip in alive:
        try: hostname = socket.gethostbyaddr(ip)[0]
        except OSError: hostname = None
        result.append({"ip": ip, "mac": arps.get(ip), "hostname": hostname, "status": "online", "seen_at": datetime.now(timezone.utc)})
    return result

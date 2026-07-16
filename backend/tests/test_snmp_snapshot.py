from app import snmp_client


def test_port_snapshot_combines_fdb_arp_and_pvid(monkeypatch):
    monkeypatch.setattr(snmp_client, "get_switch_ports", lambda *args: [
        {"port": 7, "description": "Desk", "status": "up", "mode": "Access", "speed": "1000 Mbps"},
    ])
    monkeypatch.setattr(snmp_client, "get_mac_table", lambda *args: [
        {"port": 7, "mac": "aa:bb:cc:dd:ee:ff", "bridge_port": 7},
    ])
    monkeypatch.setattr(snmp_client, "get_arp_table", lambda *args: [
        {"ip": "192.168.10.7", "mac": "aa:bb:cc:dd:ee:ff"},
    ])

    class Item:
        oid_index = "7"
        value = "7"

    class Session:
        def walk(self, oid):
            return [Item()] if oid == snmp_client.OID_BRIDGE_PORT_IF_INDEX else []

    monkeypatch.setattr(snmp_client, "_snmp_session", lambda *args: Session())

    result = snmp_client.get_switch_port_snapshot("192.168.0.2")

    assert result[0]["mac_count"] == 1
    assert result[0]["macs"] == ["aa:bb:cc:dd:ee:ff"]
    assert result[0]["ips"] == ["192.168.10.7"]


def test_lab_profile_is_independent_copy():
    from app.lab import get_profile

    first = get_profile("access-switch")
    first["ports"][0]["description"] = "changed"
    assert get_profile("access-switch")["ports"][0]["description"] == "Workstation-01"

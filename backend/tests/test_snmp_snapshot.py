from app import snmp_client


def test_mac_table_reads_fdb_port_column_and_maps_bridge_port(monkeypatch):
    class Item:
        def __init__(self, oid_index, value):
            self.oid_index = oid_index
            self.value = value

    class Session:
        def walk(self, oid):
            if oid == snmp_client.OID_BRIDGE_PORT_IF_INDEX:
                return [Item("7", "101")]
            if oid == snmp_client.OID_FDB_PORT:
                return [Item("170.187.204.221.238.255", "7")]
            raise AssertionError(f"Unexpected OID: {oid}")

    monkeypatch.setattr(snmp_client, "_snmp_session", lambda *args: Session())

    assert snmp_client.get_mac_table("192.168.0.2") == [
        {"mac": "aa:bb:cc:dd:ee:ff", "port": 101, "bridge_port": 7}
    ]


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


def test_ping_device_uses_unprivileged_socket(monkeypatch):
    captured = {}

    class Result:
        is_alive = True

    def fake_ping(ip, **kwargs):
        captured.update({"ip": ip, **kwargs})
        return Result()

    monkeypatch.setattr(snmp_client, "ping", fake_ping)

    assert snmp_client.ping_device("192.168.0.2") is True
    assert captured["privileged"] is False

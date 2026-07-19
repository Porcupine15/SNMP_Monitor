import logging
from easysnmp import Session, exceptions
from icmplib import ping
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Константы для OID
OID_SYS_NAME = '1.3.6.1.2.1.1.5.0'
OID_SYS_DESCR = '1.3.6.1.2.1.1.1.0'
OID_SYS_UPTIME = '1.3.6.1.2.1.1.3.0'
OID_IF_INDEX = '1.3.6.1.2.1.2.2.1.1'
OID_IF_DESCR = '1.3.6.1.2.1.2.2.1.2'
OID_IF_OPER_STATUS = '1.3.6.1.2.1.2.2.1.8'
OID_IF_ALIAS = '1.3.6.1.2.1.31.1.1.1.18'   # ifAlias
OID_IF_SPEED = '1.3.6.1.2.1.2.2.1.5'
OID_FDB_ADDRESS = '1.3.6.1.2.1.17.4.3.1.1'  # dot1dTpFdbAddress
OID_FDB_PORT = '1.3.6.1.2.1.17.4.3.1.2'  # dot1dTpFdbPort
OID_BRIDGE_PORT_IF_INDEX = '1.3.6.1.2.1.17.1.4.1.2'  # dot1dBasePortIfIndex
OID_DOT1Q_PVID = '1.3.6.1.2.1.17.7.1.4.5.1.1'  # dot1qPvid, indexed by bridge port
OID_FDB_STATUS = '1.3.6.1.2.1.17.4.3.1.3'
OID_ARP_IP = '1.3.6.1.2.1.4.22.1.2'  # ipNetToMediaPhysAddress
OID_ARP_MAC = '1.3.6.1.2.1.4.22.1.3'  # ipNetToMediaNetAddress
OID_ARP_TYPE = '1.3.6.1.2.1.4.22.1.4'
OID_TONER = '1.3.6.1.2.1.43.11.1.1.9.1.1'  # пример для принтеров


def ping_device(ip: str, timeout: float = 2.0) -> bool:
    """Проверяет доступность устройства по ICMP ping."""
    try:
        result = ping(ip, count=1, timeout=timeout, privileged=False)
        return result.is_alive
    except Exception as e:
        logger.error(f"Ping error {ip}: {e}")
        return False


def _snmp_session(ip: str, community: str = 'public', version: str = 'v2c',
                  snmp_user: Optional[str] = None,
                  snmp_auth: Optional[str] = None,
                  snmp_priv: Optional[str] = None) -> Session:
    """Создаёт SNMP-сессию. Поддерживает v1, v2c, v3."""
    if version == 'v3':
        if not snmp_user or not snmp_auth:
            raise ValueError("SNMPv3 requires a security username and authentication password")
        return Session(
            hostname=ip,
            version=3,
            security_username=snmp_user,
            security_level='authPriv' if snmp_priv else 'authNoPriv',
            auth_protocol='SHA',
            auth_password=snmp_auth,
            privacy_protocol='AES' if snmp_priv else None,
            privacy_password=snmp_priv or '',
            timeout=2,
            retries=1,
        )
    else:
        version_int = 1 if version == 'v1' else 2
        return Session(hostname=ip, community=community, version=version_int, timeout=2, retries=1)


def _format_mac(value: str) -> str:
    """Normalises an SNMP octet string or an OID index to aa:bb:cc:dd:ee:ff."""
    value = str(value).strip()
    if "." in value and all(part.isdigit() for part in value.split(".")):
        octets = [int(part) for part in value.split(".")]
        if len(octets) == 6 and all(0 <= part <= 255 for part in octets):
            return ":".join(f"{part:02x}" for part in octets)
    compact = "".join(char for char in value if char in "0123456789abcdefABCDEF")
    if len(compact) == 12:
        return ":".join(compact[index:index + 2].lower() for index in range(0, 12, 2))
    return value.lower()


def _ip_from_arp_index(oid_index: str) -> str:
    """ipNetToMedia is indexed as ifIndex.ipv4; return only the IPv4 portion."""
    parts = str(oid_index).split('.')
    if len(parts) >= 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts[-4:]):
        return '.'.join(parts[-4:])
    return str(oid_index)


def get_device_info(ip: str, community: str = 'public', version: str = 'v2c',
                    snmp_user: Optional[str] = None,
                    snmp_auth: Optional[str] = None,
                    snmp_priv: Optional[str] = None) -> Dict[str, Any]:
    """Получает основную информацию об устройстве (sysName, sysDescr, sysUptime)."""
    try:
        session = _snmp_session(ip, community, version, snmp_user, snmp_auth, snmp_priv)
        sys_name = session.get(OID_SYS_NAME).value
        sys_descr = session.get(OID_SYS_DESCR).value
        sys_uptime = session.get(OID_SYS_UPTIME).value
        return {
            'hostname': sys_name,
            'model': sys_descr[:100],  # обрезаем для краткости
            'uptime': sys_uptime,
            'status': 'online'
        }
    except (exceptions.EasySNMPError, ValueError) as e:
        logger.warning(f"SNMP error for {ip}: {e}")
        return {}


def get_switch_ports(ip: str, community: str = 'public', version: str = 'v2c',
                     snmp_user: Optional[str] = None,
                     snmp_auth: Optional[str] = None,
                     snmp_priv: Optional[str] = None) -> List[Dict[str, Any]]:
    """Получает список портов коммутатора с их описанием и статусом."""
    try:
        session = _snmp_session(ip, community, version, snmp_user, snmp_auth, snmp_priv)
        # Получаем все порты (ifIndex, ifDescr, ifOperStatus, ifAlias, ifSpeed)
        indexes = {}
        for item in session.walk(OID_IF_INDEX):
            indexes[item.oid_index] = {'ifIndex': int(item.value)}

        for item in session.walk(OID_IF_DESCR):
            if item.oid_index in indexes:
                indexes[item.oid_index]['description'] = item.value

        for item in session.walk(OID_IF_OPER_STATUS):
            if item.oid_index in indexes:
                status = int(item.value)
                # 1 - up, 2 - down, 3 - testing, 4 - unknown, 5 - dormant, 6 - notPresent, 7 - lowerLayerDown
                indexes[item.oid_index]['status'] = 'up' if status == 1 else 'down'

        for item in session.walk(OID_IF_ALIAS):
            if item.oid_index in indexes:
                indexes[item.oid_index]['alias'] = item.value

        for item in session.walk(OID_IF_SPEED):
            if item.oid_index in indexes:
                speed = int(item.value)
                # скорость в битах/с, переводим в Мбит/с
                indexes[item.oid_index]['speed'] = f"{speed // 1000000} Mbps" if speed > 0 else ''

        # Собираем список
        ports = []
        for idx, data in indexes.items():
            # Пропускаем порты без описания (обычно это неинтересные порты)
            ports.append({
                'port': data['ifIndex'],
                'description': data.get('description', ''),
                'status': data.get('status', 'unknown'),
                'mode': 'Trunk' if 'trunk' in data.get('alias', '').lower() else 'Access',
                'speed': data.get('speed', '')
            })
        return ports
    except (exceptions.EasySNMPError, ValueError) as e:
        logger.error(f"SNMP error getting ports for {ip}: {e}")
        return []


def get_mac_table(ip: str, community: str = 'public', version: str = 'v2c',
                  snmp_user: Optional[str] = None,
                  snmp_auth: Optional[str] = None,
                  snmp_priv: Optional[str] = None) -> List[Dict[str, Any]]:
    """Получает MAC-адреса с привязкой к портам."""
    try:
        session = _snmp_session(ip, community, version, snmp_user, snmp_auth, snmp_priv)
        macs = []
        bridge_port_to_ifindex = {
            int(item.oid_index): int(item.value)
            for item in session.walk(OID_BRIDGE_PORT_IF_INDEX)
        }
        # The FDB port column is indexed by MAC and returns a bridge-port number,
        # which must then be mapped to the interface ifIndex.
        for item in session.walk(OID_FDB_PORT):
            bridge_port = int(item.value)
            macs.append({
                'mac': _format_mac(item.oid_index),
                'port': bridge_port_to_ifindex.get(bridge_port),
                'bridge_port': bridge_port,
            })
        return macs
    except (exceptions.EasySNMPError, ValueError) as e:
        logger.error(f"SNMP error getting MAC table for {ip}: {e}")
        return []


def get_arp_table(ip: str, community: str = 'public', version: str = 'v2c',
                  snmp_user: Optional[str] = None,
                  snmp_auth: Optional[str] = None,
                  snmp_priv: Optional[str] = None) -> List[Dict[str, Any]]:
    """Получает ARP-таблицу (IP -> MAC)."""
    try:
        session = _snmp_session(ip, community, version, snmp_user, snmp_auth, snmp_priv)
        arp = {}
        # ipNetToMediaPhysAddress (1.3.6.1.2.1.4.22.1.2) содержит MAC для каждого IP
        for item in session.walk(OID_ARP_IP):
            # item.oid_index содержит IP адрес в формате "192.168.1.1"
            ip_addr = _ip_from_arp_index(item.oid_index)
            mac_str = _format_mac(item.value)
            arp[ip_addr] = {'ip': ip_addr, 'mac': mac_str}

        # Можно также получить дополнительно тип, но не обязательно
        return list(arp.values())
    except (exceptions.EasySNMPError, ValueError) as e:
        logger.error(f"SNMP error getting ARP table for {ip}: {e}")
        return []


def get_switch_port_snapshot(ip: str, community: str = 'public', version: str = 'v2c',
                             snmp_user: Optional[str] = None,
                             snmp_auth: Optional[str] = None,
                             snmp_priv: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns ports enriched with PVID, learned MAC addresses and ARP-derived IPs.

    PVID is read from the standard Q-BRIDGE-MIB. Some switches do not expose
    Q-BRIDGE-MIB; in that case the field is ``None`` rather than guessed.
    """
    ports = get_switch_ports(ip, community, version, snmp_user, snmp_auth, snmp_priv)
    if not ports:
        return []

    macs = get_mac_table(ip, community, version, snmp_user, snmp_auth, snmp_priv)
    arp_entries = get_arp_table(ip, community, version, snmp_user, snmp_auth, snmp_priv)
    ips_by_mac: Dict[str, List[str]] = {}
    for entry in arp_entries:
        ips_by_mac.setdefault(entry['mac'], []).append(entry['ip'])

    macs_by_port: Dict[int, List[str]] = {}
    for entry in macs:
        if entry['port'] is not None:
            macs_by_port.setdefault(entry['port'], []).append(entry['mac'])

    pvid_by_ifindex: Dict[int, int] = {}
    try:
        session = _snmp_session(ip, community, version, snmp_user, snmp_auth, snmp_priv)
        bridge_port_to_ifindex = {
            int(item.oid_index): int(item.value)
            for item in session.walk(OID_BRIDGE_PORT_IF_INDEX)
        }
        for item in session.walk(OID_DOT1Q_PVID):
            if_index = bridge_port_to_ifindex.get(int(item.oid_index))
            if if_index is not None:
                pvid_by_ifindex[if_index] = int(item.value)
    except Exception as exc:
        logger.info("Q-BRIDGE-MIB unavailable for %s: %s", ip, exc)

    for port in ports:
        learned_macs = sorted(set(macs_by_port.get(port['port'], [])))
        learned_ips = sorted({
            ip_address for mac in learned_macs for ip_address in ips_by_mac.get(mac, [])
        })
        port['pvid'] = pvid_by_ifindex.get(port['port'])
        port['mac_count'] = len(learned_macs)
        port['macs'] = learned_macs
        port['ips'] = learned_ips
    return ports


def get_printer_toner(ip: str, community: str = 'public', version: str = 'v2c',
                      snmp_user: Optional[str] = None,
                      snmp_auth: Optional[str] = None,
                      snmp_priv: Optional[str] = None) -> int:
    """Получает уровень тонера для принтера (в процентах)."""
    try:
        session = _snmp_session(ip, community, version, snmp_user, snmp_auth, snmp_priv)
        # OID для тонера может отличаться, пример для многих принтеров
        # 1.3.6.1.2.1.43.11.1.1.9.1.1 - это первый картридж
        toner = session.get(OID_TONER).value
        # Иногда значение в процентах, иногда в абсолютных единицах
        return int(toner) if toner.isdigit() else 0
    except (exceptions.EasySNMPError, ValueError) as e:
        logger.error(f"SNMP error getting toner for {ip}: {e}")
        return 0

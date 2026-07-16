"""Run on a macOS/Linux host in the LAN, not inside Docker."""
import argparse, json, os, re, socket, subprocess, time
from urllib.request import Request, urlopen

API_URL = os.getenv('SNMP_MONITOR_URL', 'http://localhost:8000/api/clients/agent-sync')
TOKEN = os.environ['LAN_AGENT_TOKEN']
ARP = re.compile(r'\(([^)]+)\) at ([0-9a-f:]{17})', re.I)

def clients():
    output = subprocess.check_output(['arp', '-a'], text=True, stderr=subprocess.DEVNULL)
    result = []
    for ip, mac in ARP.findall(output):
        try: name = socket.gethostbyaddr(ip)[0]
        except OSError: name = None
        result.append({'ip': ip, 'mac': mac.lower(), 'hostname': name})
    return result

def sync():
    payload = json.dumps({'clients': clients()}).encode()
    request = Request(API_URL, data=payload, headers={'Content-Type':'application/json','X-LAN-Agent-Token':TOKEN})
    with urlopen(request, timeout=15) as response:
        print(response.read().decode(), flush=True)

def main():
    parser = argparse.ArgumentParser(description='Sync the host ARP table with SNMP Monitor')
    parser.add_argument('--watch', action='store_true', help='keep synchronizing until stopped')
    parser.add_argument('--interval', type=int, default=60, help='watch interval in seconds (minimum 30)')
    args = parser.parse_args()
    while True:
        sync()
        if not args.watch:
            break
        time.sleep(max(args.interval, 30))

if __name__ == '__main__':
    main()

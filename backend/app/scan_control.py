"""Process-wide guard for expensive active network scans.

Production runs a single Uvicorn worker because APScheduler is embedded in the
API process, so one lock protects both discovery endpoints from overlapping.
"""

from threading import Lock


active_network_scan = Lock()

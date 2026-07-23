import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from integrations.container_services import ContainerServicesMonitor, DockerServiceClient, SERVICE_CONTAINERS


def test_requested_services_are_monitored():
    assert set(SERVICE_CONTAINERS) == {
        "Plex", "Jellyfin", "Flaresolverr", "Prowlarr", "Radarr", "Sonarr", "Seerr",
        "Tautulli", "Tracearr", "Traefik", "Wizarr", "Linkstack", "Nginx",
        "qBittorrent Radarr", "qBittorrent Sonarr",
    }


def test_docker_port_formatting():
    ports = {"8080/tcp": [{"HostPort": "6882"}], "6881/udp": None}
    assert DockerServiceClient._format_ports(ports) == "6882→8080/tcp, 6881/udp"


def test_uptime_formatting():
    started = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2, hours=3, minutes=4)).isoformat()
    assert ContainerServicesMonitor._uptime(started).startswith("2 j 3 h")

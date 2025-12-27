import pytest

import macblock.system_dns as system_dns


def test_parse_listnetworkserviceorder_maps_devices():
    text = """An asterisk (*) denotes that a network service is disabled.
(1) Wi-Fi
(Hardware Port: Wi-Fi, Device: en0)

(2) Thunderbolt Bridge
(Hardware Port: Thunderbolt Bridge, Device: bridge0)

(3) Tailscale
(Hardware Port: io.tailscale.ipn.macsys, Device: )
"""

    mapping = system_dns._parse_networksetup_listnetworkserviceorder(text)
    assert mapping["Wi-Fi"] == "en0"
    assert mapping["Thunderbolt Bridge"] == "bridge0"
    assert mapping["Tailscale"] is None


def test_compute_managed_services_uses_device_map(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        system_dns,
        "list_enabled_network_services",
        lambda: ["Wi-Fi", "Tailscale", "Thunderbolt Bridge"],
    )
    monkeypatch.setattr(
        system_dns,
        "list_network_service_devices",
        lambda: {"Wi-Fi": "en0", "Tailscale": None, "Thunderbolt Bridge": "bridge0"},
    )

    managed = system_dns.compute_managed_services(exclude=set())
    assert [s.name for s in managed] == ["Thunderbolt Bridge", "Wi-Fi"]
    by_name = {s.name: s.device for s in managed}
    assert by_name["Wi-Fi"] == "en0"
    assert by_name["Thunderbolt Bridge"] == "bridge0"

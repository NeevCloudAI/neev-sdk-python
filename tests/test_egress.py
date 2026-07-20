"""Unit tests for the egress convenience helper."""

from neevai._egress import build_egress


def test_build_egress_none_when_unset():
    assert build_egress(None, None) is None
    assert build_egress(False, []) is None


def test_build_egress_allow_internet_emits_routes():
    # The gate alone is a server-side no-op, so the 0.0.0.0/0 + ::/0 routes must ride along.
    assert build_egress(True, None) == {
        "mode": "allow_list",
        "allow_internet": True,
        "allow": [{"host": "0.0.0.0/0"}, {"host": "::/0"}],
    }


def test_build_egress_allow_hosts_no_internet_gate():
    assert build_egress(None, ["github.com", "*.npmjs.org"]) == {
        "mode": "allow_list",
        "allow_internet": False,
        "allow": [{"host": "github.com"}, {"host": "*.npmjs.org"}],
    }


def test_build_egress_internet_and_hosts_combine():
    assert build_egress(True, ["10.0.0.0/8"]) == {
        "mode": "allow_list",
        "allow_internet": True,
        "allow": [{"host": "0.0.0.0/0"}, {"host": "::/0"}, {"host": "10.0.0.0/8"}],
    }

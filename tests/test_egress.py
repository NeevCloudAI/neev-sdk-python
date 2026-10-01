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


def _update_body(params, **kwargs):
    from neevai._egress import prepare_update_body
    from neevai.types import UpdateSandboxParams

    return prepare_update_body(UpdateSandboxParams, params, **kwargs)


def test_update_body_accepts_egress_add_and_remove():
    body = _update_body(
        {
            "egress_add": {
                "allow": [{"host": "api.github.com", "ports": [443], "protocol": "TCP"}]
            },
            "egress_remove": {"allow": [{"host": "old.example.com"}]},
        }
    )
    assert body == {
        "egress_add": {"allow": [{"host": "api.github.com", "ports": [443], "protocol": "TCP"}]},
        "egress_remove": {"allow": [{"host": "old.example.com"}]},
    }


def test_update_body_rejects_egress_with_egress_add():
    import pytest

    from neevai.errors import NeevAIError

    with pytest.raises(NeevAIError, match="cannot be combined"):
        _update_body({"egress": {"mode": "deny_all"}, "egress_add": {"allow": [{"host": "a.com"}]}})


def test_update_body_rejects_convenience_with_egress_remove():
    import pytest

    from neevai.errors import NeevAIError

    with pytest.raises(NeevAIError, match="cannot be combined"):
        _update_body({"egress_remove": {"allow": [{"host": "a.com"}]}}, allow_internet=True)


def test_update_body_empty_names_every_field():
    import pytest

    from neevai.errors import NeevAIError

    with pytest.raises(NeevAIError) as exc:
        _update_body({})
    for field in ("resources", "egress", "egress_add", "egress_remove"):
        assert f"`{field}`" in str(exc.value)

import pytest
from yuki_mcp.limits import GRATIS_TEKST, resolve_limit


def test_standaard_900():
    c = resolve_limit({})
    assert c.limit == 900 and not c.warnings


@pytest.mark.parametrize("v", ["500", "900", "950", "1000"])
def test_tot_en_met_1000_zonder_akkoord(v):
    c = resolve_limit({"YUKI_DAILY_LIMIT": v})
    assert c.limit == int(v) and c.warnings == []


def test_boven_1000_zonder_akkoord_wordt_begrensd():
    c = resolve_limit({"YUKI_DAILY_LIMIT": "1500"})
    assert c.limit == 1000 and any("begrensd op 1000" in w for w in c.warnings)
    assert any(GRATIS_TEKST in w for w in c.warnings)


def test_boven_1000_met_akkoord_geeft_kostenwaarschuwing():
    c = resolve_limit({"YUKI_DAILY_LIMIT": "1500", "YUKI_DAILY_LIMIT_APPROVAL": "ref-1"})
    assert c.limit == 1500 and c.approved_over_free
    assert any("kosten" in w and "WAARSCHUWING" in w for w in c.warnings)


@pytest.mark.parametrize("v", ["abc", "0", "-5"])
def test_ongeldig_valt_terug_op_900(v):
    c = resolve_limit({"YUKI_DAILY_LIMIT": v})
    assert c.limit == 900 and c.warnings


def test_901e_call_blokkeert(tmp_path):
    from yuki_mcp.clientfactory import PluginQuota
    q = PluginQuota(tmp_path, resolve_limit({}))
    for _ in range(900):
        q.reserve("dom", method="X")
    with pytest.raises(Exception) as ei:
        q.reserve("dom", method="X")
    assert "limit" in str(ei.value).lower() or "limiet" in str(ei.value).lower()
    assert q.status("dom").calls == 900


def test_gratis_zin_in_status_tool(rpc):
    d = rpc.req("tools/list")["result"]["tools"]
    st = next(t for t in d if t["name"] == "yuki_status")
    assert "Yuki: 1000 calls per domein per dag zijn gratis." in st["description"]

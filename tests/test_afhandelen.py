"""Controle na afhandelen: leesfunctie rond Backoffice.GetWorkflow. Synthetische [Voorbeeld]-data."""
import json

import pytest
from conftest import fault

from yuki_mcp import afhandelen as af

A = "[Vennootschapsnaam] BV"
DOC = "11111111-2222-3333-4444-555555555555"


def data(r):
    assert r["isError"] is False, r
    return json.loads(r["content"][0]["text"])


def wf(*ids):
    return "<ArrayOfWorkflowItem>" + "".join(f"<WorkflowItem><DocumentID>{i}</DocumentID><Subject>[Voorbeeld]</Subject></WorkflowItem>" for i in ids) + "</ArrayOfWorkflowItem>"


def test_document_nog_in_workflow(rpc, fake):
    fake.responses["GetWorkflow"] = wf(DOC, "aaaaaaaa-0000-0000-0000-000000000001")
    r = data(rpc.call("yuki_afhandeling_controle", administratie=A, document_id="D:" + DOC))
    assert r["uitkomst"] == af.NOG and r["afgehandeld"] is False and r["zekerheid"] == "hoog" and r["methode"] == "Backoffice.GetWorkflow"


def test_document_niet_meer_in_workflow(rpc, fake):
    fake.responses["GetWorkflow"] = wf("aaaaaaaa-0000-0000-0000-000000000001")
    r = data(rpc.call("yuki_afhandeling_controle", administratie=A, document_id=DOC))
    assert r["uitkomst"] == af.WEG and r["afgehandeld"] is True and r["zekerheid"] == "midden" and "verifieer" in r["uitleg"]


def test_lege_workflow_en_onbekend_formaat(rpc, fake):
    fake.responses["GetWorkflow"] = "<ArrayOfWorkflowItem></ArrayOfWorkflowItem>"
    assert data(rpc.call("yuki_afhandeling_controle", administratie=A, document_id=DOC))["uitkomst"] == af.WEG
    fake.responses["GetWorkflow"] = "<Workflow><Naam>x</Naam><Aantal>3</Aantal></Workflow>"
    r = data(rpc.call("yuki_afhandeling_controle", administratie=A, document_id=DOC, vernieuwen=True))
    assert r["uitkomst"] == af.ONBEPAALD and r["afgehandeld"] is None


def test_fout_geeft_fout_en_geen_schrijfcall(rpc, fake):
    fake.responses["GetWorkflow"] = fault("fout")
    assert rpc.call("yuki_afhandeling_controle", administratie=A, document_id=DOC)["isError"] is True
    assert all(m == "GetWorkflow" or not m.startswith(("Process", "Upload", "Update")) for m in fake.methods())


def test_ongeldig_id_en_alleen_lezen():
    with pytest.raises(ValueError):
        af.beoordeel([], "x")
    from yuki_mcp.transport import is_allowed
    assert is_allowed("Backoffice", "GetWorkflow") and not is_allowed("Backoffice", "ProcessWorkflow")
    assert af.document_id("D:abc12345") == "abc12345"


def test_tool_is_alleen_lezen_geannoteerd(rpc):
    t = next(x for x in rpc.req("tools/list")["result"]["tools"] if x["name"] == "yuki_afhandeling_controle")
    assert t["annotations"]["readOnlyHint"] is True and t["annotations"]["destructiveHint"] is False

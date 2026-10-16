"""Each requirement's verdict on the reference product sheet, plus counterfactual sheets
showing that the rules react to the evidence rather than to keywords."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit  # noqa: E402
from audit import Status  # noqa: E402

EXPECTED = {
    "REQ-01": Status.AMBIGU, "REQ-02": Status.AMBIGU, "REQ-03": Status.AMBIGU,
    "REQ-04": Status.SATISFAIT, "REQ-05": Status.SATISFAIT, "REQ-06": Status.NON_SATISFAIT,
    "REQ-07": Status.AMBIGU, "REQ-08": Status.NON_SATISFAIT, "REQ-09": Status.SATISFAIT,
    "REQ-10": Status.SATISFAIT, "REQ-11": Status.AMBIGU,
}


def run(product_text: str = audit.PRODUCT_TEXT) -> dict:
    reqs = audit.parse_requirements(audit.REGULATORY_TEXT)
    product = audit.parse_product_sheet(product_text)
    return {r.requirement.id: r for r in audit.evaluate_all(reqs, product)}


def test_all_requirements_extracted():
    reqs = audit.parse_requirements(audit.REGULATORY_TEXT)
    assert [r.id for r in reqs] == [f"REQ-{i:02d}" for i in range(1, 12)]


@pytest.mark.parametrize("req_id,status", EXPECTED.items())
def test_reference_verdict(req_id, status):
    assert run()[req_id].status == status


def test_every_non_satisfied_or_ambiguous_case_says_what_is_missing():
    for r in run().values():
        if r.status != Status.SATISFAIT:
            assert r.reason
        if r.status == Status.AMBIGU:
            assert r.missing


def test_translations_fix_req06():
    text = audit.PRODUCT_TEXT.replace("PRÉSENTE en français", "PRÉSENTE en français, italien, portugais")
    assert run(text)["REQ-06"].status == Status.SATISFAIT


def test_unknown_market_is_ambiguous_not_satisfied():
    text = audit.PRODUCT_TEXT.replace("France, Italie, Portugal", "France, Belgique")
    assert run(text)["REQ-06"].status == Status.AMBIGU


def test_full_lifecycle_risk_assessment_fixes_req08():
    text = audit.PRODUCT_TEXT.replace(
        "RÉALISÉE pour la phase d'utilisation uniquement",
        "RÉALISÉE sur le cycle de vie complet")
    assert run(text)["REQ-08"].status == Status.SATISFAIT


def test_iso_and_en_numbering_of_the_same_standard_match():
    assert audit._normalize_standard("EN ISO 13850") == audit._normalize_standard("EN 13850")

#!/usr/bin/env python3
"""
Parser unit tests for the journal database ETL pipeline.

Small inline fixtures only, no live network calls or real downloaded
files - fast, deterministic, safe to run anywhere. Matches this repo's
existing plain assert-script test convention (see tests/test_reference_validator.py).

Run: python3 tests/test_journal_etl_parsers.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "etl"))

from src.db.issn_utils import all_issns, normalize_issn  # noqa: E402


def test_normalize_issn():
    assert normalize_issn("0065230X") == "0065-230X"
    assert normalize_issn("0065-230x") == "0065-230X"
    assert normalize_issn("1069-6563") == "1069-6563"
    assert normalize_issn("") == ""
    assert normalize_issn(None) == ""
    assert normalize_issn("not-an-issn") == ""
    print("test_normalize_issn OK")


def test_all_issns_dedupe_and_order():
    result = all_issns("0065-230X", ["0065-230X", "1069-6563", None, "bad"])
    assert result == ["0065-230X", "1069-6563"], result
    print("test_all_issns_dedupe_and_order OK")


def test_doaj_apc_parsing():
    import ingest_doaj

    row_with_apc = {"APC": "Yes", "APC amount": "1500 USD"}
    has_apc, amount, currency = ingest_doaj._parse_apc(row_with_apc)
    assert has_apc is True and amount == 1500.0 and currency == "USD", (has_apc, amount, currency)

    row_no_apc = {"APC": "No", "APC amount": ""}
    has_apc, amount, currency = ingest_doaj._parse_apc(row_no_apc)
    assert has_apc is False and amount is None and currency is None
    print("test_doaj_apc_parsing OK")


def test_doaj_bulk_row_shape():
    import csv
    import io

    import ingest_doaj

    csv_text = (
        "Journal title,Journal ISSN (print version),Journal EISSN (online version),"
        "Publisher,Country of publisher,APC,APC amount,"
        "Journal waiver policy (for developing country authors etc),"
        "Waiver policy information URL,Journal license,Review process\n"
        "Sample Journal,1234-5678,,Sample Publisher,India,Yes,1200 USD,"
        "Full waivers for low-income countries,https://example.org/waiver,CC BY,"
        "Double blind peer review\n"
    )
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) == 1
    row = rows[0]
    issn_l = normalize_issn(row.get("Journal ISSN (print version)"))
    assert issn_l == "1234-5678"
    has_apc, amount, currency = ingest_doaj._parse_apc(row)
    assert has_apc is True and amount == 1200.0 and currency == "USD"
    print("test_doaj_bulk_row_shape OK")


def test_elsevier_list_type_classification():
    import ingest_elsevier_apc

    assert ingest_elsevier_apc._list_type("Hybrid Open Access") == "hybrid"
    assert ingest_elsevier_apc._list_type("Full Open Access") == "fully-oa"
    assert ingest_elsevier_apc._list_type("Subsidized") == "other"
    assert ingest_elsevier_apc._list_type(None) == "other"
    print("test_elsevier_list_type_classification OK")


def test_ieee_title_normalization_matches_variants():
    import ingest_ieee_apc

    a = ingest_ieee_apc._normalize_title("Aerospace and Electronic Systems, IEEE Trans.")
    b = ingest_ieee_apc._normalize_title("IEEE Transactions on Aerospace and Electronic Systems")
    assert a == b, (a, b)
    print("test_ieee_title_normalization_matches_variants OK")


def test_wiley_issn_from_numeric_cell_preserves_leading_zero():
    import ingest_wiley_apc

    assert ingest_wiley_apc._issn_from_cell(16870409) == "1687-0409"
    assert ingest_wiley_apc._issn_from_cell(1780782) == "0178-0782"  # leading zero recovered
    assert ingest_wiley_apc._issn_from_cell(None) == ""
    print("test_wiley_issn_from_numeric_cell_preserves_leading_zero OK")


if __name__ == "__main__":
    test_normalize_issn()
    test_all_issns_dedupe_and_order()
    test_doaj_apc_parsing()
    test_doaj_bulk_row_shape()
    test_elsevier_list_type_classification()
    test_ieee_title_normalization_matches_variants()
    test_wiley_issn_from_numeric_cell_preserves_leading_zero()
    print("\nAll journal ETL parser tests passed.")

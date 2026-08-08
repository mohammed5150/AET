"""Tests for SDS-004: asset registry import, classification, circuits."""

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.models.geometry import Coordinate, parse_coordinate
from app.models.project import SourceInput
from app.modules.asset_engine import (
    RegistryColumnMap,
    XlsxAssetRegistryReader,
    classify_asset_type,
    derive_circuit,
)

HEADERS = [
    "id",
    "name",
    "assetClass",
    "mainArea",
    "subArea",
    "utmZone",
    "utmE",
    "utmN",
    "serialNumber",
]

ROWS = [
    [
        1,
        "TCC102-01/067",
        "ADB-BI-GG-S-INSET-8IN-2x40W",
        "ST",
        "E4N",
        "40 N",
        261833.45,
        2703563.93,
        "SN-1",
    ],
    [
        2,
        "HH.E4.035",
        "AGL PIT",
        "AUX",
        "AGL Pits - South",
        "40 N",
        261000.0,
        2703000.0,
        None,
    ],
    [
        3,
        "SBC13L.06.021",
        "ADB-BI-RR-INSET-8IN-48W",
        "NT",
        "K3P1",
        "40 N",
        262000.0,
        2704000.0,
        None,
    ],
    [4, "RRM.1", "RRM", "ST", "RRM", "40 N", 263000.0, 2705000.0, None],
    [5, "SIGN.01", "SGN", "ST", "B", None, None, None, None],
    [6, None, "SGN", "ST", "B", None, None, None, None],
    [
        7,
        "EL.NBASE.13088",
        "ADB_NBASE",
        "SR",
        "D4 on Rwy",
        "40 N",
        264000.0,
        2706000.0,
        None,
    ],
]


def _registry(path: Path, headers=None, rows=ROWS) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Assets"
    sheet.append(headers or HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path


def _source(path: Path) -> SourceInput:
    return SourceInput(
        project_id="p1",
        path=str(path),
        file_hash="h",
        file_format="xlsx",
    )


def test_registry_rows_become_classified_assets(tmp_path: Path):
    path = _registry(tmp_path / "assets.xlsx")
    result = XlsxAssetRegistryReader().read(_source(path))
    assert result.skipped_rows == 1  # the row with no name
    by_name = {asset.name: asset for asset in result.assets}
    assert len(by_name) == 6

    fitting = by_name["TCC102-01/067"]
    assert fitting.asset_type == "light-fitting"
    assert fitting.attributes["circuit"] == "TCC102"
    assert fitting.attributes["circuit_family"] == "TCC"
    assert fitting.attributes["asset_class"] == "ADB-BI-GG-S-INSET-8IN-2x40W"
    assert fitting.attributes["main_area"] == "ST"
    assert fitting.attributes["serial_number"] == "SN-1"
    assert fitting.location == Coordinate(
        easting=261833.45, northing=2703563.93, zone="40 N"
    )
    assert fitting.snapshot_id == ""
    assert fitting.attributes["registry_input_id"]

    assert by_name["HH.E4.035"].asset_type == "agl-pit"
    assert by_name["HH.E4.035"].attributes["circuit_family"] == "HH"
    assert "circuit" not in by_name["HH.E4.035"].attributes
    assert by_name["SBC13L.06.021"].attributes["circuit"] == "SBC13L"
    assert by_name["RRM.1"].asset_type == "rrm"
    assert by_name["SIGN.01"].asset_type == "sign"
    assert by_name["SIGN.01"].location is None
    assert by_name["EL.NBASE.13088"].asset_type == "base"


def test_missing_required_columns_fail_with_names(tmp_path: Path):
    path = _registry(
        tmp_path / "bad.xlsx",
        headers=["name", "mainArea"],
        rows=[["X.1", "ST"]],
    )
    from app.core.errors import InputError

    with pytest.raises(InputError) as excinfo:
        XlsxAssetRegistryReader().read(_source(path))
    assert "assetClass" in str(excinfo.value)


def test_missing_file_fails_with_input_error(tmp_path: Path):
    from app.core.errors import InputError

    with pytest.raises(InputError):
        XlsxAssetRegistryReader().read(_source(tmp_path / "missing.xlsx"))


def test_custom_column_map(tmp_path: Path):
    path = _registry(
        tmp_path / "mapped.xlsx",
        headers=["Tag", "Class", "Area"],
        rows=[["TCC1.1", "AGL PIT", "ST"]],
    )
    columns = RegistryColumnMap(name="Tag", asset_class="Class", main_area="Area")
    result = XlsxAssetRegistryReader(columns=columns).read(_source(path))
    assert result.assets[0].name == "TCC1.1"
    assert result.assets[0].asset_type == "agl-pit"


@pytest.mark.parametrize(
    ("asset_class", "expected"),
    [
        ("AGL PIT", "agl-pit"),
        ("CCH-OMNI-B-INSET-8IN-48W", "light-fitting"),
        ("ADB-UNI-C-ELEV-150W", "light-fitting"),
        ("TWE-in", "light-fitting"),
        ("STB-in2", "light-fitting"),
        ("TCL-s_gg", "light-fitting"),
        ("LIL_yy_C", "light-fitting"),
        ("RGL", "light-fitting"),
        ("STL", "light-fitting"),
        ("SGN", "sign"),
        ("SG", "sign"),
        ("RRM", "rrm"),
        ("ADB_NBASE", "base"),
        ("Base-8", "base"),
        ("CRBLK", "base"),
        ("Lightpoles", "lightpole"),
        ("CCR-CRE-30KVA", "ccr"),
        ("CCR-CCH-7.5KVA", "ccr"),
        ("High Mast Light", "high-mast"),
        ("Highway Streetlight", "streetlight"),
        ("Apron Stand", "apron-floodlight"),
        ("Halogen Obstruction Lamp", "obstruction-light"),
        ("LED Obstruction Lamp", "obstruction-light"),
        ("TRL_ rg", "traffic-light"),
        ("WDI", "wdi"),
        ("TRA", "extra-asset"),
        ("FCU_1", "extra-asset"),
        ("RRS", "extra-asset"),
        ("LVO", "extra-asset"),
        ("LVO-SOUTH", "extra-asset"),
        ("LVO-MTA", "extra-asset"),
        ("Mystery Thing", "other"),
    ],
)
def test_classification_rules(asset_class: str, expected: str):
    assert classify_asset_type(asset_class) == expected


@pytest.mark.parametrize(
    ("asset_class", "name", "expected"),
    [
        ("Generic", "TCCPA1.02.019", "light-fitting"),
        ("*U", "TECPA2.01.057", "light-fitting"),
        ("Generic", "SGC13L.02.077", "sign"),
        ("Generic", "RGC105.01.002", "light-fitting"),
        ("Generic", "HH.E4.001", "agl-pit"),
        ("Generic", "XYZ.1", "other"),
        ("Generic", "", "other"),
        # Class rules always win over the name fallback
        ("AGL PIT", "TCC1.1", "agl-pit"),
    ],
)
def test_name_based_fallback(asset_class: str, name: str, expected: str):
    assert classify_asset_type(asset_class, name=name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("TCC102-01/067", {"circuit_family": "TCC", "circuit": "TCC102"}),
        ("SBC13L.06.021", {"circuit_family": "SBC", "circuit": "SBC13L"}),
        ("HH.E4.035", {"circuit_family": "HH"}),
        ("RRM.1", {"circuit_family": "RRM"}),
        ("123.45", {}),
    ],
)
def test_circuit_derivation(name: str, expected: dict):
    assert derive_circuit(name) == expected


def test_unusable_ordinates_keep_the_row_and_preserve_the_raw_values(tmp_path: Path):
    # SDS-009 §5.4: a bad cell degrades one field, it does not reject the row.
    path = _registry(
        tmp_path / "bad-coords.xlsx",
        rows=[
            [
                1,
                "TCC1.01",
                "AGL PIT",
                "ST",
                "E4N",
                "40 N",
                "not-a-number",
                "2703",
                None,
            ],
            [2, "TCC1.02", "AGL PIT", "ST", "E4N", "40 N", "nan", "2703", None],
            [3, "TCC1.03", "AGL PIT", "ST", "E4N", "40 N", None, None, None],
        ],
    )
    result = XlsxAssetRegistryReader().read(_source(path))
    assert result.skipped_rows == 0
    by_name = {asset.name: asset for asset in result.assets}
    assert len(by_name) == 3

    unparsed = by_name["TCC1.01"]
    assert unparsed.location is None
    assert unparsed.attributes["utm_unparsed"] == "not-a-number|2703"
    assert unparsed.attributes["utm_zone"] == "40 N"

    # "nan" parses as a float but is not a position (SDS-009 §5.3).
    assert by_name["TCC1.02"].location is None
    assert by_name["TCC1.02"].attributes["utm_unparsed"] == "nan|2703"

    # Genuinely absent ordinates are not "unparsed", just missing.
    absent = by_name["TCC1.03"]
    assert absent.location is None
    assert "utm_unparsed" not in absent.attributes
    assert absent.attributes["utm_zone"] == "40 N"


def test_elevation_is_not_read_from_the_default_export():
    # The AUH export carries no elevation column; assets stay planar.
    assert parse_coordinate("1", "2").elevation is None

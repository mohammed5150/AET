"""Tests for SDS-010: asset derivation from drawings."""

import logging
from pathlib import Path

import ezdxf
import pytest

from aet.models.drawing import DrawingEntity, DrawingSnapshot
from aet.models.geometry import Coordinate
from aet.models.project import SourceInput
from aet.modules.asset_engine import (
    AssetEngine,
    DerivationRule,
    DxfAssetExtractor,
    derive_circuit,
)
from aet.modules.drawing_engine import DrawingEngine


def _insert(
    block: str,
    layer: str = "AGL-MISC",
    position: tuple[float, float] = (261800.0, 2703500.0),
    handle: str = "1A",
    attribs: dict[str, str] | None = None,
) -> DrawingEntity:
    attributes = {"name": block}
    attributes.update(attribs or {})
    return DrawingEntity(
        entity_type="insert",
        layer=layer,
        attributes=attributes,
        geometry={"position": [position[0], position[1]], "rotation": 0.0},
        geometry_ref=handle,
    )


def _snapshot(*entities: DrawingEntity, units: str = "6") -> DrawingSnapshot:
    return DrawingSnapshot(
        project_id="p1",
        source_input_id="in1",
        entities=list(entities),
        metadata={"units": units, "entity_count": str(len(entities))},
    )


# -- §9.1 a matched reference becomes a fully attributed asset --------------


def test_matched_reference_becomes_an_asset_with_provenance():
    entity = _insert(
        "TCL_LIGHT",
        layer="AGL-TCL",
        position=(261800.5, 2703500.25),
        handle="2F",
        attribs={"attr.TAG": "TCC102-01/067", "attr.CIRCUIT": "TCC102"},
    )
    snapshot = _snapshot(entity)
    result = DxfAssetExtractor().derive(snapshot)

    assert result.derived == 1
    [asset] = result.collection.assets
    assert asset.asset_type == "light-fitting"
    assert asset.name == "TCC102-01/067"
    assert asset.location == Coordinate(easting=261800.5, northing=2703500.25)
    # Provenance is what will let a derived asset be compared to a registry one.
    assert asset.snapshot_id == snapshot.snapshot_id
    assert asset.source_entity_ids == [entity.entity_id]
    assert asset.project_id == "p1"
    assert asset.attributes["block_name"] == "TCL_LIGHT"
    assert asset.attributes["layer"] == "AGL-TCL"
    assert asset.attributes["handle"] == "2F"
    # Captured ATTRIBs pass through unchanged.
    assert asset.attributes["attr.CIRCUIT"] == "TCC102"
    assert asset.attributes["attr.TAG"] == "TCC102-01/067"


# -- §9.2 block name beats layer -------------------------------------------


def test_block_rule_wins_over_a_conflicting_layer_rule():
    # A fitting block drawn on a sign layer is a fitting: the block names the
    # thing, the layer only names where it was drawn.
    rules = (
        DerivationRule("sign", layer=r"SIGN"),
        DerivationRule("light-fitting", block=r"^TCL"),
    )
    result = DxfAssetExtractor(rules).derive(
        _snapshot(_insert("TCL_LIGHT", layer="AGL-SIGNS"))
    )
    assert [a.asset_type for a in result.collection.assets] == ["light-fitting"]


def test_layer_classifies_when_the_block_name_is_generic():
    result = DxfAssetExtractor().derive(
        _snapshot(_insert("GENERIC_SYMBOL", layer="AGL-TCL-EDGE"))
    )
    assert [a.asset_type for a in result.collection.assets] == ["light-fitting"]


# -- §9.3 unmatched references are skipped, not classified "other" ----------


def test_unmatched_reference_is_skipped_and_counted():
    # A drawing is full of non-asset blocks; deriving them as "other" would
    # bury the real assets (SDS-010 §5.1).
    result = DxfAssetExtractor().derive(
        _snapshot(
            _insert("TITLE_BLOCK", layer="BORDER"),
            _insert("NORTH_ARROW", layer="BORDER"),
            _insert("TCL_LIGHT", layer="AGL-TCL"),
        )
    )
    assert result.derived == 1
    assert result.skipped_unclassified == 2
    assert result.skipped_unresolved == 0
    assert [a.asset_type for a in result.collection.assets] == ["light-fitting"]
    assert "other" not in {a.asset_type for a in result.collection.assets}


# -- §9.4 references whose content is unseen are declined -------------------


@pytest.mark.parametrize(
    "flag",
    [{"block_is_xref": "true"}, {"block_nested_inserts": "3"}],
)
def test_unresolved_references_yield_no_assets(flag: dict[str, str]):
    # SDS-008 records these so this stage can decline rather than invent an
    # asset whose content it never saw.
    result = DxfAssetExtractor().derive(
        _snapshot(_insert("TCL_LIGHT", layer="AGL-TCL", attribs=flag))
    )
    assert result.derived == 0
    assert result.skipped_unresolved == 1
    assert result.skipped_unclassified == 0


# -- §9.5 only block references are candidates ------------------------------


def test_non_insert_entities_never_yield_assets():
    line = DrawingEntity(
        entity_type="line",
        layer="AGL-TCL",
        geometry={"points": [[0.0, 0.0], [10.0, 0.0]]},
        geometry_ref="3A",
    )
    text = DrawingEntity(
        entity_type="text",
        layer="AGL-TCL",
        attributes={"content": "TCC102-01/067"},
        geometry={"position": [1.0, 1.0]},
        geometry_ref="3B",
    )
    result = DxfAssetExtractor().derive(_snapshot(line, text))
    assert result.derived == 0
    assert result.skipped_unclassified == 0
    assert result.skipped_unresolved == 0


# -- §9.6 naming ------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "expected_source"),
    [("TAG", "attrib:TAG"), ("ASSET_TAG", "attrib:ASSET_TAG"), ("ID", "attrib:ID")],
)
def test_name_comes_from_the_first_preferred_tag(tag: str, expected_source: str):
    result = DxfAssetExtractor().derive(
        _snapshot(_insert("TCL_LIGHT", layer="AGL-TCL", attribs={f"attr.{tag}": "X.1"}))
    )
    [asset] = result.collection.assets
    assert asset.name == "X.1"
    assert asset.attributes["name_source"] == expected_source


def test_preferred_tags_are_consulted_in_order():
    result = DxfAssetExtractor().derive(
        _snapshot(
            _insert(
                "TCL_LIGHT",
                layer="AGL-TCL",
                attribs={"attr.ID": "fallback", "attr.TAG": "preferred"},
            )
        )
    )
    assert result.collection.assets[0].name == "preferred"


def test_untagged_reference_is_named_from_block_and_handle_stably():
    snapshot = _snapshot(_insert("TCL_LIGHT", layer="AGL-TCL", handle="4C"))
    first = DxfAssetExtractor().derive(snapshot).collection.assets[0]
    second = DxfAssetExtractor().derive(snapshot).collection.assets[0]

    assert first.name == "TCL_LIGHT:4C"
    assert first.attributes["name_source"] == "handle"
    # Stable across re-derivation, so results are comparable between runs.
    assert second.name == first.name


def test_blank_tag_value_falls_through_to_the_handle():
    result = DxfAssetExtractor().derive(
        _snapshot(
            _insert(
                "TCL_LIGHT", layer="AGL-TCL", handle="5D", attribs={"attr.TAG": "  "}
            )
        )
    )
    assert result.collection.assets[0].name == "TCL_LIGHT:5D"


# -- §9.7 the UTM zone is configured, never inferred ------------------------


def test_zone_is_unknown_unless_configured():
    # A DXF states coordinates, never the projection they are in.
    result = DxfAssetExtractor().derive(
        _snapshot(_insert("TCL_LIGHT", layer="AGL-TCL"))
    )
    assert result.collection.assets[0].location is not None
    assert result.collection.assets[0].location.zone == ""


def test_configured_zone_appears_on_every_derived_coordinate():
    result = DxfAssetExtractor(utm_zone=" 40 N ").derive(
        _snapshot(
            _insert("TCL_LIGHT", layer="AGL-TCL", handle="1"),
            _insert("TCL_LIGHT", layer="AGL-TCL", handle="2"),
        )
    )
    zones = {a.location.zone for a in result.collection.assets if a.location}
    assert zones == {"40 N"}


def test_unknown_zone_still_measures_but_a_stated_one_guards():
    extractor = DxfAssetExtractor()
    result = extractor.derive(
        _snapshot(
            _insert("TCL_LIGHT", layer="AGL-TCL", position=(0.0, 0.0), handle="1"),
            _insert("TCL_LIGHT", layer="AGL-TCL", position=(30.0, 40.0), handle="2"),
        )
    )
    first, second = (a.location for a in result.collection.assets)
    assert first is not None
    assert second is not None
    assert first.distance_to(second) == pytest.approx(50.0)


def test_reference_without_a_usable_position_has_no_coordinate():
    entity = _insert("TCL_LIGHT", layer="AGL-TCL")
    entity.geometry = {"rotation": 0.0}
    result = DxfAssetExtractor().derive(_snapshot(entity))
    assert result.derived == 1
    assert result.collection.assets[0].location is None


# -- §9.8 drawing units ----------------------------------------------------


def test_drawing_units_are_recorded():
    result = DxfAssetExtractor().derive(
        _snapshot(_insert("TCL_LIGHT", layer="AGL-TCL"), units="6")
    )
    assert result.collection.assets[0].attributes["drawing_units"] == "6"


def test_non_metre_units_are_flagged(caplog):
    # Every downstream distance is in metres; millimetres would yield positions
    # a thousand times too large.
    with caplog.at_level(logging.WARNING, logger="aet"):
        DxfAssetExtractor().derive(
            _snapshot(_insert("TCL_LIGHT", layer="AGL-TCL"), units="4")
        )
    assert any(
        "neither metres nor unstated" in record.message for record in caplog.records
    )


@pytest.mark.parametrize("units", ["0", "6", ""])
def test_metric_and_unstated_units_are_not_flagged(units: str, caplog):
    with caplog.at_level(logging.WARNING, logger="aet"):
        DxfAssetExtractor().derive(
            _snapshot(_insert("TCL_LIGHT", layer="AGL-TCL"), units=units)
        )
    assert not [r for r in caplog.records if "neither metres" in r.message]


# -- §9.9 circuit attributes agree with the registry -----------------------


@pytest.mark.parametrize(
    "name", ["TCC102-01/067", "SBC13L.06.021", "HH.E4.035", "RRM.1"]
)
def test_circuit_attributes_match_the_registry_parser(name: str):
    # A drawing asset and a registry asset on one circuit must carry identical
    # circuit attributes, or the two can never be compared.
    result = DxfAssetExtractor().derive(
        _snapshot(_insert("TCL_LIGHT", layer="AGL-TCL", attribs={"attr.TAG": name}))
    )
    [asset] = result.collection.assets
    for key, value in derive_circuit(name).items():
        assert asset.attributes[key] == value


# -- §9.10 no relations are asserted ---------------------------------------


def test_no_relations_are_derived():
    # Circuit ordering is a property of cable routing, which the normalized
    # model does not represent (SDS-010 §7.3).
    result = DxfAssetExtractor().derive(
        _snapshot(
            _insert(
                "TCL_LIGHT", layer="AGL-TCL", handle="1", attribs={"attr.CIRCUIT": "T1"}
            ),
            _insert(
                "TCL_LIGHT", layer="AGL-TCL", handle="2", attribs={"attr.CIRCUIT": "T1"}
            ),
        )
    )
    assert result.collection.relations == []


# -- §9.11 the pipeline derives by default --------------------------------


def _agl_dxf(path: Path) -> None:
    document = ezdxf.new("R2010", setup=False)
    document.header["$INSUNITS"] = 6
    document.layers.add("AGL-TCL")
    document.layers.add("BORDER")

    fitting = document.blocks.new("TCL_LIGHT")
    fitting.add_circle((0, 0), 0.25)
    fitting.add_attdef("TAG", (0, 1), dxfattribs={"height": 0.2})
    document.blocks.new("TITLE_BLOCK").add_line((0, 0), (1, 0))

    msp = document.modelspace()
    for index in range(3):
        reference = msp.add_blockref(
            "TCL_LIGHT",
            (261800 + index * 15, 2703500),
            dxfattribs={"layer": "AGL-TCL"},
        )
        reference.add_auto_attribs({"TAG": f"TCC102-01/{index + 1:03d}"})
    msp.add_blockref("TITLE_BLOCK", (0, 0), dxfattribs={"layer": "BORDER"})
    document.saveas(path)


def test_asset_engine_derives_by_default(tmp_path: Path):
    path = tmp_path / "taxiway.dxf"
    _agl_dxf(path)
    source = SourceInput(
        project_id="p1", path=str(path), file_hash="h", file_format="dxf"
    )
    snapshot = DrawingEngine().normalize(source).payload
    assert snapshot is not None

    outcome = AssetEngine().derive(snapshot, correlation_id="c1")
    assert outcome.success
    assert outcome.payload is not None
    names = sorted(asset.name for asset in outcome.payload.assets)
    assert names == ["TCC102-01/001", "TCC102-01/002", "TCC102-01/003"]
    assert {a.asset_type for a in outcome.payload.assets} == {"light-fitting"}
    # The title block is not an asset.
    assert all(
        a.attributes["block_name"] == "TCL_LIGHT" for a in outcome.payload.assets
    )


def test_explicit_null_extractor_still_derives_nothing(tmp_path: Path):
    from aet.modules.asset_engine import NullAssetExtractor

    path = tmp_path / "taxiway.dxf"
    _agl_dxf(path)
    source = SourceInput(
        project_id="p1", path=str(path), file_hash="h", file_format="dxf"
    )
    snapshot = DrawingEngine().normalize(source).payload
    assert snapshot is not None
    outcome = AssetEngine(extractor=NullAssetExtractor()).derive(snapshot)
    assert outcome.success
    assert outcome.payload is not None
    assert outcome.payload.assets == []

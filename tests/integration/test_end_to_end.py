"""End-to-end pipeline test with custom strategies and plugins.

Exercises the SDS-002 §7 data flow — registration, ingestion, normalization,
asset derivation, validation, reporting — with a fake interpreter, extractor,
and a plugin-provided validation rule, checking traceability along the way.
"""

from pathlib import Path

from app.core.plugins import (
    Plugin,
    PluginCategory,
    PluginManifest,
    PluginRuntime,
)
from app.models.asset import Asset
from app.models.drawing import DrawingEntity, DrawingLayer, DrawingSnapshot
from app.models.validation import Severity, ValidationResult
from app.modules.asset_engine import AssetCollection, AssetEngine
from app.modules.drawing_engine import DrawingEngine
from app.modules.ingestion import IngestionEngine
from app.services.use_cases import ApplicationService


class FakeInterpreter:
    """Normalizes any source into one layer with two light entities."""

    def interpret(self, source):
        entities = [
            DrawingEntity(
                entity_type="block-ref",
                layer="AGL-EDGE",
                attributes={"block": "EDGE_LIGHT"},
            ),
            DrawingEntity(
                entity_type="block-ref",
                layer="AGL-EDGE",
                attributes={"block": "EDGE_LIGHT"},
            ),
        ]
        return DrawingSnapshot(
            project_id=source.project_id,
            source_input_id=source.input_id,
            layers=[DrawingLayer(name="AGL-EDGE", entity_count=2)],
            entities=entities,
            metadata={"source_path": source.path},
        )


class FakeExtractor:
    """Derives one asset per drawing entity, keeping provenance."""

    def extract(self, snapshot):
        assets = [
            Asset(
                project_id=snapshot.project_id,
                snapshot_id=snapshot.snapshot_id,
                asset_type="edge-light",
                name=f"EL-{index:03d}",
                source_entity_ids=[entity.entity_id],
            )
            for index, entity in enumerate(snapshot.entities, start=1)
        ]
        return AssetCollection(assets=assets)


class MinimumAssetsRule:
    rule_id = "agl.minimum-assets"
    description = "Projects must derive at least one asset"

    def evaluate(self, context):
        passed = len(context.assets) > 0
        return [
            ValidationResult(
                rule_id=self.rule_id,
                severity=Severity.INFO if passed else Severity.ERROR,
                passed=passed,
                message=f"{len(context.assets)} asset(s) derived",
            )
        ]


class RulePackPlugin(Plugin):
    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id="aet.test.rule-pack",
            name="Test Rule Pack",
            version="0.1.0",
            category=PluginCategory.VALIDATION_RULE,
        )

    def activate(self, context) -> object:
        return MinimumAssetsRule()


def test_real_dxf_flow_with_default_wiring(dxf_file: Path):
    """SDS-003: a real DXF file flows through the default service wiring."""
    service = ApplicationService()
    project = service.create_project("DXF Demo").payload
    assert project is not None
    assert service.import_drawing(project.project_id, dxf_file).success

    processed = service.process_drawings(project.project_id)
    assert processed.success
    assert processed.payload is not None
    assert processed.payload.succeeded

    reported = service.generate_report(project.project_id)
    assert reported.success
    assert reported.payload is not None
    _, artifacts = reported.payload
    assert "Drawing snapshots: 1" in artifacts[0].content


def test_dwg_to_report_flow_with_plugin_rule(tmp_path: Path):
    plugins = PluginRuntime()
    assert plugins.register(RulePackPlugin()).success

    service = ApplicationService(
        ingestion=IngestionEngine(),
        drawing=DrawingEngine(interpreter=FakeInterpreter()),
        assets=AssetEngine(extractor=FakeExtractor()),
        plugins=plugins,
    )

    project = service.create_project("ZIA Apron Z2").payload
    assert project is not None
    drawing = tmp_path / "z2-apron.dwg"
    drawing.write_bytes(b"pretend this is a dwg")
    imported = service.import_drawing(project.project_id, drawing)
    assert imported.success

    processed = service.process_drawings(project.project_id)
    assert processed.success
    assert processed.payload is not None
    assert processed.payload.succeeded
    stages = [str(record.stage) for record in processed.payload.records]
    assert stages == ["interpretation", "asset-derivation"]

    # rules=[] opts out of the SDS-005 standard pack, isolating plugin rules
    validated = service.validate_project(project.project_id, rules=[])
    assert validated.success
    assert validated.payload is not None
    findings = validated.payload.results
    assert len(findings) == 1
    assert findings[0].rule_id == "agl.minimum-assets"
    assert findings[0].passed

    reported = service.generate_report(project.project_id)
    assert reported.success
    assert reported.payload is not None
    report, artifacts = reported.payload
    assert report.summary == "2 asset(s), 1 finding(s)"
    content = artifacts[0].content
    assert "ZIA Apron Z2" in content
    assert "Derived assets: 2" in content
    assert "agl.minimum-assets" in content

"""Asset derivation module (SDS-002 §8.6, SDS-004, SDS-010)."""

from aet.modules.asset_engine.derivation import (
    DEFAULT_DERIVATION_RULES,
    DEFAULT_NAME_TAGS,
    DerivationResult,
    DerivationRule,
    DxfAssetExtractor,
)
from aet.modules.asset_engine.engine import (
    AssetCollection,
    AssetEngine,
    AssetExtractor,
    NullAssetExtractor,
)
from aet.modules.asset_engine.registry import (
    RegistryColumnMap,
    RegistryImport,
    XlsxAssetRegistryReader,
    classify_asset_type,
    derive_circuit,
)

__all__ = [
    "DEFAULT_DERIVATION_RULES",
    "DEFAULT_NAME_TAGS",
    "AssetCollection",
    "AssetEngine",
    "AssetExtractor",
    "DerivationResult",
    "DerivationRule",
    "DxfAssetExtractor",
    "NullAssetExtractor",
    "RegistryColumnMap",
    "RegistryImport",
    "XlsxAssetRegistryReader",
    "classify_asset_type",
    "derive_circuit",
]

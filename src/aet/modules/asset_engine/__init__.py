"""Asset derivation module (SDS-002 §8.6, SDS-004)."""

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
    "AssetCollection",
    "AssetEngine",
    "AssetExtractor",
    "NullAssetExtractor",
    "RegistryColumnMap",
    "RegistryImport",
    "XlsxAssetRegistryReader",
    "classify_asset_type",
    "derive_circuit",
]

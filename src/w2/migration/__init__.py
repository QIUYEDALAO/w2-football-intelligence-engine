"""W1 to W2 migration dry-run and shadow comparison foundation."""

from w2.migration.foundation import (
    DATA_DOMAINS,
    MigrationDecision,
    MigrationDryRunEngine,
    MigrationSourceAsset,
    TransformContract,
    build_default_contracts,
    build_source_inventory,
    quarantine_registry,
    sha256_file,
)
from w2.migration.shadow import (
    ShadowComparisonEngine,
    ShadowComparisonRecord,
    ShadowRunManifest,
    W1SnapshotAdapter,
    W2SnapshotAdapter,
)

__all__ = [
    "DATA_DOMAINS",
    "MigrationDecision",
    "MigrationDryRunEngine",
    "MigrationSourceAsset",
    "ShadowComparisonEngine",
    "ShadowComparisonRecord",
    "ShadowRunManifest",
    "TransformContract",
    "W1SnapshotAdapter",
    "W2SnapshotAdapter",
    "build_default_contracts",
    "build_source_inventory",
    "quarantine_registry",
    "sha256_file",
]

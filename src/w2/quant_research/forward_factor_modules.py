"""Locate the accepted F1R-B recording modules without copying them.

`scripts/quant/` stays the single authoritative source of the F1R-B wiring:
the version check, the capture identity, the source-time rules, the batch
builder and the database sink are all still there, unchanged, and the tests
that pin them still read them there.

A released image does not carry `scripts/`, so the same files are force-included
into the wheel at `w2/quant_research/_f1r_b/` by `pyproject.toml`. This module
resolves exactly one directory and loads the modules from it. There is no second
copy of the code and no second hash writer: the loader decides *where* the
modules are, never *what* they say.

Resolution order, both determinate:

1. the in-package directory, which exists when `w2` was installed from a wheel;
2. a source checkout, recognised only by an explicit project root -- a
   `pyproject.toml` next to `scripts/quant/` -- never by searching the disk.

Anything else fails closed. A path guessed from the module's own location is
what made the released dashboard 500 with
`SC21_FACTOR_ROLE_AUTHORITY_MATRIX_NOT_FOUND`, so the checkout branch is
narrow on purpose: it requires `parents[2]` to be `src` and the project root to
carry its own `pyproject.toml`.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Where the wheel puts the force-included modules.
PACKAGE_MODULE_DIRNAME = "_f1r_b"
#: Where a source checkout keeps them.
CHECKOUT_MODULE_DIRNAME = Path("scripts/quant")

#: Every file the entry modules pull in, by the sibling name each one loads.
REQUIRED_FILENAMES = (
    "f1p_forward_factor_contract.py",
    "f1r_a0_offline_factor_recorder.py",
    "f1r_b_source_capture.py",
    "f1r_b_production_ports.py",
    "f1r_b_production_recording_integration.py",
    "f1r_b_observation_store.py",
)

#: The two entry points. Each loads its own siblings from its own directory, so
#: loading these two is enough and the sibling set stays the F1R-B module's
#: business rather than this loader's.
ENTRY_MODULES = (
    ("w2_f1r_b_integration", "f1r_b_production_recording_integration.py"),
    ("w2_f1r_b_observation_store", "f1r_b_observation_store.py"),
)

CHECKOUT_REPO_ROOT_PARENTS = 3
CHECKOUT_SRC_PARENT_INDEX = 2


class ForwardFactorModulesNotFound(FileNotFoundError):
    """The F1R-B modules could not be located. Never defaulted."""


def _complete(directory: Path) -> bool:
    return all((directory / name).is_file() for name in REQUIRED_FILENAMES)


def package_module_dir() -> Path:
    return Path(__file__).resolve().parent / PACKAGE_MODULE_DIRNAME


def checkout_module_dir() -> Path | None:
    """The source checkout's `scripts/quant/`, or None.

    Requires the module to sit at `<root>/src/w2/quant_research/`, so the path
    is derived from an explicit project root rather than assumed.
    """
    module_path = Path(__file__).resolve()
    parents = module_path.parents
    if len(parents) <= CHECKOUT_REPO_ROOT_PARENTS:
        return None
    if parents[CHECKOUT_SRC_PARENT_INDEX].name != "src":
        return None
    root = parents[CHECKOUT_REPO_ROOT_PARENTS]
    if not (root / "pyproject.toml").is_file():
        return None
    return root / CHECKOUT_MODULE_DIRNAME


def module_dir() -> Path:
    """The one directory the F1R-B modules are loaded from, or a refusal."""
    installed = package_module_dir()
    if _complete(installed):
        return installed
    checkout = checkout_module_dir()
    if checkout is not None and _complete(checkout):
        return checkout
    raise ForwardFactorModulesNotFound(
        "FORWARD_FACTOR_MODULES_NOT_FOUND:"
        f"package={installed}:checkout={checkout}"
    )


def _load(directory: Path, module_name: str, filename: str) -> Any:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, directory / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True, kw_only=True)
class ForwardFactorModules:
    """The F1R-B modules the production recorder reuses, loaded, not copied."""

    directory: Path
    integration: Any
    store: Any

    @property
    def ports(self) -> Any:
        return self.integration.ports

    @property
    def capture(self) -> Any:
        return self.integration.capture

    @property
    def contract(self) -> Any:
        return self.integration.contract

    @property
    def recorder(self) -> Any:
        return self.integration.recorder


def load_modules() -> ForwardFactorModules:
    directory = module_dir()
    loaded = {
        name: _load(directory, name, filename) for name, filename in ENTRY_MODULES
    }
    return ForwardFactorModules(
        directory=directory,
        integration=loaded["w2_f1r_b_integration"],
        store=loaded["w2_f1r_b_observation_store"],
    )

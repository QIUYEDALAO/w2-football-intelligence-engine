from __future__ import annotations

from dataclasses import dataclass

from w2.historical.dataset import AsOfSample
from w2.historical.leakage import assert_no_random_time_split


@dataclass(frozen=True)
class SplitResult:
    train: tuple[AsOfSample, ...]
    validation: tuple[AsOfSample, ...]
    test: tuple[AsOfSample, ...]


def _ordered(samples: list[AsOfSample]) -> list[AsOfSample]:
    return sorted(
        samples, key=lambda sample: (sample.kickoff_utc, sample.fixture_id, sample.as_of_time)
    )


def chronological_split(
    samples: list[AsOfSample], train_ratio: float = 0.6, validation_ratio: float = 0.2
) -> SplitResult:
    ordered = _ordered(samples)
    train_end = max(1, int(len(ordered) * train_ratio))
    validation_end = max(train_end + 1, int(len(ordered) * (train_ratio + validation_ratio)))
    return SplitResult(
        tuple(ordered[:train_end]),
        tuple(ordered[train_end:validation_end]),
        tuple(ordered[validation_end:]),
    )


def rolling_split(samples: list[AsOfSample], train_size: int, test_size: int) -> list[SplitResult]:
    ordered = _ordered(samples)
    splits: list[SplitResult] = []
    for start in range(0, max(0, len(ordered) - train_size - test_size + 1), test_size):
        train = ordered[start : start + train_size]
        test = ordered[start + train_size : start + train_size + test_size]
        splits.append(SplitResult(tuple(train), (), tuple(test)))
    return splits


def expanding_split(
    samples: list[AsOfSample], min_train_size: int, test_size: int
) -> list[SplitResult]:
    ordered = _ordered(samples)
    splits: list[SplitResult] = []
    for train_end in range(min_train_size, len(ordered), test_size):
        splits.append(
            SplitResult(
                tuple(ordered[:train_end]), (), tuple(ordered[train_end : train_end + test_size])
            )
        )
    return splits


def walk_forward_split(
    samples: list[AsOfSample], initial_train_size: int, step_size: int
) -> list[SplitResult]:
    return expanding_split(samples, initial_train_size, step_size)


def split_by_name(name: str, samples: list[AsOfSample]) -> SplitResult | list[SplitResult]:
    assert_no_random_time_split(name)
    if name == "chronological":
        return chronological_split(samples)
    if name == "rolling":
        return rolling_split(samples, train_size=2, test_size=1)
    if name == "expanding":
        return expanding_split(samples, min_train_size=2, test_size=1)
    if name == "walk-forward":
        return walk_forward_split(samples, initial_train_size=2, step_size=1)
    raise ValueError(f"unsupported splitter {name}")

"""Compare expected task effects with the effects recorded by a run."""

from __future__ import annotations

from app.models import Run, Task, Verdict


def verify(task: Task, run: Run) -> Verdict:
    matched = []
    missing = []
    claimed: set[int] = set()

    for expected in task.expected_effects:
        for index, effect in enumerate(run.effects):
            if index in claimed:
                continue
            if effect.tool == expected.tool and all(
                effect.args.get(key) == value for key, value in expected.match.items()
            ):
                claimed.add(index)
                matched.append(expected)
                break
        else:
            missing.append(expected)

    unexpected = [effect for index, effect in enumerate(run.effects) if index not in claimed]
    return Verdict(
        passed=not missing and not unexpected,
        matched=matched,
        missing=missing,
        unexpected=unexpected,
        mode=run.autonomy,
        detail=f"{len(matched)} matched, {len(missing)} missing, {len(unexpected)} unexpected",
    )

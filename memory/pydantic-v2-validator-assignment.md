# Pydantic v2 — self-assignment inside `model_validator(mode='after')`

Inside a Pydantic v2 `@model_validator(mode='after')`, direct field
assignment (`self.field = value`) re-enters the validation pipeline
because Pydantic's `__setattr__` re-runs validators on assignment.
That can recurse on the very validator currently executing, either
infinite-looping or raising a confusing error.

## Symptom

A validator that derives a default for one field from another:

```python
@model_validator(mode="after")
def _resolve_primary_atc(self) -> "PharmaConfig":
    if self.sub_mode == "specialty-care" and self.primary_atc is None:
        self.primary_atc = "L01"   # ← re-runs validators
    return self
```

…raises `ValidationError` inside `__setattr__` or appears to hang as
the validator re-fires. The error is not where you'd expect; the
stacktrace points at the assignment, not at the validator.

## Root cause

Pydantic v2 routes field writes through `__setattr__`, which by
default re-runs the per-field validators (and, for `mode='after'`
validators, the model validator itself). Inside a `mode='after'`
validator, validation has already passed once — re-running it is
unwanted reentrancy.

## Fix

Use `object.__setattr__` to bypass Pydantic's `__setattr__` and write
the field directly. This is the officially-documented escape hatch
for exactly this case and is safe inside a `mode='after'` validator
because validation has already completed.

```python
@model_validator(mode="after")
def _resolve_primary_atc(self) -> "PharmaConfig":
    if self.sub_mode == "specialty-care" and self.primary_atc is None:
        object.__setattr__(self, "primary_atc", "L01")
    return self
```

**Caveat:** Only use this *inside* validators. Outside a validator,
plain `instance.field = value` is fine — letting Pydantic re-validate
is the whole point of model mutation.

## References

- Live example: `src/synth_datagen/pharma/config.py::_resolve_primary_atc`
- Pydantic v2 docs on model validators (`mode='after'` reentrancy)
- Phase 6 commit introducing the pattern: `feat(pharma): add Pydantic config with sub-mode and external-input validation`

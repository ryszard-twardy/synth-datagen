# API reference

This page is auto-generated from the docstrings of the public modules in `src/synth_datagen/`. To regenerate locally:

```bash
uv run mkdocs build --strict
```

For end-to-end runnable code, see the [`examples/`](https://github.com/ryszard-twardy/synth-datagen/tree/main/examples) directory.

## Configuration

The `config` module defines every Pydantic model the pipeline accepts.

::: synth_datagen.config

## Pipeline

The single entry point that takes a `GeneratorConfig` and writes all outputs to disk.

::: synth_datagen.pipeline.run_pipeline

## CLI

The Typer app wired up to the four scenarios plus three sub-apps. See [Quickstart](../quickstart.md) for shell usage.

::: synth_datagen.cli

## Schema builder

Topologically orders tables by FK dependency, builds PK/FK pools, and walks the `dim → fact → bridge` chain in a deterministic order.

::: synth_datagen.schema_builder

## Seeding utilities

The single `--seed` enters the pipeline through `seed_everything`, which returns the parent `SeedSequence`, a `numpy.random.Generator`, and a `Faker` instance. See [Architecture › RNG isolation](../architecture/rng-isolation.md) for why this matters.

::: synth_datagen.utils.seed_everything

::: synth_datagen.rng

## Runtime support

Helpers used by every CLI surface so missing optional runtime deps (`faker`, `pyarrow`) produce a friendly error message instead of an `ImportError` at the bottom of a stack trace.

::: synth_datagen.runtime_support

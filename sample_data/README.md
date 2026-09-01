# Sample Data

Generated local demo data lives under `sample_data/generated/`.

That directory is ignored by Git. Recreate it with:

```bash
uv run python scripts/create_demo_dataset.py create --overwrite
```

Create all local demo suites, including annotation, mask, and validation
fixtures, with:

```bash
uv run python scripts/create_demo_dataset.py create --suite all --overwrite
```

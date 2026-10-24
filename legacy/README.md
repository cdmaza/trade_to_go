# legacy/

The original scripts, kept unchanged for reference while the new package is verified.
Nothing imports from here. Delete this folder once you are happy with `src/trade_to_go/`.

| Old file | Replaced by |
|---|---|
| `extract/get_gold.py` | `src/trade_to_go/sources/bgd.py` |
| `data/store_gold.py` | `core/storage.py` (raw + staging Parquet) |
| `notify/telegram.py` | `core/telegram.py` |
| `notify/notifier.py` | `alerts/` (planned) |
| `main.py` | `cli.py` (`ttg ingest bgd`) |
| `sql/init/create_table` | `core/storage.py` `OPS_SCHEMA` |
| `data/temp/goldMinMax.json` | not ported; min/max will be a feature over staging data |

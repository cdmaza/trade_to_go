"""Success criterion 1: the implementation reproduces published results.
Targets and tolerances come from config/replication.yaml.
"""

import pandas as pd
import pytest
import yaml

from tests.conftest import REPO_ROOT
from trade_to_go.backtest.replication import compute

SPECS = yaml.safe_load((REPO_ROOT / "config" / "replication.yaml").read_text())
CASES = [(study, name) for study, spec in SPECS.items() for name in spec["targets"]]


@pytest.mark.parametrize("study,target", CASES)
def test_replicates_published_value(study, target):
    spec = SPECS[study]
    expected = spec["targets"][target]
    if expected["value"] is None:
        pytest.skip(f"{study}.{target}: published value not filled in config/replication.yaml")
    path = REPO_ROOT / spec["data"]
    if not path.exists():
        pytest.skip(f"{study}: reference data {spec['data']} not present")

    got = compute(spec, pd.read_csv(path))[target]
    assert got == pytest.approx(expected["value"], abs=expected["tolerance"]), spec["cite"]

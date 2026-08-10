import pytest


@pytest.fixture
def fixtures_dir():
    from pathlib import Path

    return Path(__file__).parent / "fixtures"

from pathlib import Path

import pytest

from gcode_toolpath import Job


@pytest.fixture
def job():
    return Job.load(Path(__file__).parents[1] / "examples/bracket.json")

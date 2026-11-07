import pytest
from scripts.timing import arrival


def test_arrival_ignores_required_time_and_slack():
    assert arrival(' 21.9012 data arrival time\n 99 data required time\n 77 slack')==21.9012


def test_arrival_ignores_repeated_negative_slack_subtraction():
    assert arrival(' 21.0994 data arrival time\n -21.0994 data arrival time\n')==21.0994


@pytest.mark.parametrize('text',['','0.0000 data arrival time','-12.0 data arrival time',
    '12.0 data arrival time\n13.0 data arrival time'])
def test_missing_zero_or_ambiguous_paths_fail(text):
    with pytest.raises(ValueError): arrival(text)

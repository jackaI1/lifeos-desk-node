import pytest
from scripts.report import summarize


COMPLETE = 'Coverage: 11/11 required bins\n' + ''.join(
    f'FIFO_COVERAGE depth={d} seed={s} hit=7 total=7\n'
    for d in [1,3,8] for s in [17,409,20261106])


def test_success_requires_all_coverage_and_passing_simulation():
    report = summarize(COMPLETE, 0)
    assert report['status']=='pass'
    assert report['coverage_hit']==report['coverage_total']==11
    assert len(report['fifo_runs'])==9


def test_failed_or_missing_coverage_never_passes():
    assert summarize(COMPLETE.replace('11/11','10/11'), 0)['status'] == 'fail'
    assert summarize(COMPLETE, 1)['status'] == 'fail'
    assert summarize('', 0)['status'] == 'fail'


@pytest.mark.parametrize('log', [COMPLETE.replace('hit=7','hit=6',1),
    COMPLETE.replace('total=7','total=0',1), COMPLETE.split('FIFO_COVERAGE')[0],
    COMPLETE+'FIFO_COVERAGE depth=8 seed=17 hit=7 total=7\n',
    COMPLETE.replace('seed=17','seed=18',1), COMPLETE+'Coverage: 11/11 required bins\n'])
def test_incomplete_duplicate_or_wrong_seed_coverage_fails(log):
    assert summarize(log,0)['status']=='fail'

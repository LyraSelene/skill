"""Behavior tests for the evidence runner; synthetic JUnit tests the gate only."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

MODULE = Path(os.environ.get('GITHUB_IMPROVER_GATE',
    str(Path(__file__).resolve().parents[1] / 'github-project-improver/scripts/evidence_gate.py')))
SPEC = importlib.util.spec_from_file_location('evidence_gate', MODULE)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def make_plan(tmp_path, xml=None, code=None):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'input.txt').write_text('v1', encoding='utf-8')
    if xml is None:
        xml = '<testsuite tests="1" failures="0" errors="0" skipped="0" />'
    if code is None:
        code = f'from pathlib import Path; Path(r"{{junit}}").write_text({xml!r}); print("executed")'
    elif '{junit}' not in code:
        code = 'report_path = r"{junit}"; ' + code
    checks = [{'id': kind, 'kind': kind, 'cwd': str(tmp_path),
               'argv': [sys.executable, '-c', code] if kind != 'format'
                       else [sys.executable, '-c', 'print("format checked")'],
               'timeout': 5} for kind in ['behavior', 'regression', 'format']]
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'snapshot_roots': [str(source)], 'checks': checks}), encoding='utf-8')
    return plan, tmp_path / 'run', source


def test_valid_evidence_is_replayable(tmp_path):
    plan, out, _ = make_plan(tmp_path)
    assert gate.run(plan, out)
    assert gate.verify(plan, out / 'receipt.json')


@pytest.mark.parametrize('xml', [
    '<testsuite tests="0" />',
    '<testsuite tests="3" skipped="3" />',
    '<testsuite tests="1" failures="1" />',
    '<testsuite tests="1" errors="1" />',
    '<testsuite tests="1" skipped="2" />',
    '<testsuite tests="-1" />',
    '<testsuites />',
    'broken xml',
])
def test_exit_zero_is_insufficient(tmp_path, xml):
    plan, out, _ = make_plan(tmp_path, xml=xml)
    assert not gate.run(plan, out)
    with pytest.raises(ValueError):
        gate.verify(plan, out / 'receipt.json')


@pytest.mark.parametrize('code', ['print("no report")', 'raise SystemExit(7)'])
def test_missing_or_failed_check(tmp_path, code):
    plan, out, _ = make_plan(tmp_path, code=code)
    assert not gate.run(plan, out)


def test_timeout_is_not_success(tmp_path):
    plan, out, _ = make_plan(tmp_path, code='import time; time.sleep(2)')
    data = json.loads(plan.read_text())
    for check in data['checks']:
        if check['kind'] != 'format':
            check['timeout'] = 0.05
    plan.write_text(json.dumps(data))
    assert not gate.run(plan, out)


@pytest.mark.parametrize('artifact', ['source', 'plan', 'log', 'junit', 'receipt-checks'])
def test_changed_evidence_is_rejected(tmp_path, artifact):
    plan, out, source = make_plan(tmp_path)
    assert gate.run(plan, out)
    receipt = out / 'receipt.json'
    if artifact == 'source':
        (source / 'input.txt').write_text('v2')
    elif artifact == 'plan':
        plan.write_text(plan.read_text() + '\n')
    elif artifact == 'log':
        (out / 'behavior.log').write_text('changed')
    elif artifact == 'junit':
        (out / 'behavior.xml').write_text('<testsuite tests="999" />')
    else:
        data = json.loads(receipt.read_text(encoding='utf-8'))
        data['checks'].pop()
        receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        gate.verify(plan, receipt)


def test_source_change_during_execution_is_rejected(tmp_path):
    plan, out, source = make_plan(tmp_path)
    data = json.loads(plan.read_text())
    data['checks'][0]['argv'][2] += f'; Path({str(source / "input.txt")!r}).write_text("v2")'
    plan.write_text(json.dumps(data))
    assert not gate.run(plan, out)


def test_missing_required_kind_is_rejected(tmp_path):
    plan, out, _ = make_plan(tmp_path)
    data = json.loads(plan.read_text())
    data['checks'].pop()
    plan.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        gate.run(plan, out)


def test_output_cannot_contaminate_source_or_reuse_receipt(tmp_path):
    plan, out, source = make_plan(tmp_path)
    with pytest.raises(ValueError):
        gate.run(plan, source / 'evidence')
    assert gate.run(plan, out)
    with pytest.raises(FileExistsError):
        gate.run(plan, out)


def test_nested_suites_do_not_double_count(tmp_path):
    plan, out, _ = make_plan(tmp_path, xml='<testsuites><testsuite tests="2"><testsuite tests="2" skipped="1" /></testsuite></testsuites>')
    assert gate.run(plan, out)
    data = json.loads((out / 'receipt.json').read_text(encoding='utf-8'))
    assert data['checks'][0]['counts']['tests'] == 2

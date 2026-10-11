"""Run required checks and bind their evidence to a source snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

IGNORED = {'.git', '__pycache__', '.pytest_cache', '.venv'}
KINDS = {'behavior', 'regression', 'format'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_plan(path):
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    roots = plan['snapshot_roots']
    if not roots or any(not Path(p).is_absolute() or not Path(p).exists() for p in roots):
        raise ValueError('Snapshot roots must be existing absolute paths')
    ids = set()
    kinds = set()
    for check in plan['checks']:
        check_id = check['id']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', check_id) or check_id in ids:
            raise ValueError('Check IDs must be unique safe filenames')
        ids.add(check_id)
        kinds.add(check['kind'])
        if check['kind'] not in KINDS:
            raise ValueError('Unknown check kind')
        if not Path(check['cwd']).is_absolute() or not Path(check['cwd']).is_dir():
            raise ValueError('Each cwd must be an existing absolute directory')
        argv = check['argv']
        if not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv):
            raise ValueError('argv must be a nonempty list of strings')
        if check['kind'] != 'format' and not any('{junit}' in a for a in argv):
            raise ValueError('Behavior and regression checks require fresh JUnit output')
        if not isinstance(check.get('timeout', 120), (int, float)) or check.get('timeout', 120) <= 0:
            raise ValueError('timeout must be positive')
    if kinds != KINDS:
        raise ValueError('behavior, regression and format checks are all required')
    return plan


def snapshot(roots):
    files = {}
    for root in roots:
        root = Path(root).resolve()
        candidates = [root] if root.is_file() else root.rglob('*')
        for path in candidates:
            if path.is_file() and not any(part in IGNORED for part in path.relative_to(root.parent if root.is_file() else root).parts):
                files[str(path.resolve())] = digest(path)
    if not files:
        raise ValueError('Source snapshot cannot be empty')
    return files


def test_counts(path):
    root = ET.parse(path).getroot()
    suites = [s for s in root.iter('testsuite') if not list(s.iter('testsuite'))[1:]]
    if not suites:
        raise ValueError('JUnit contains no test suites')
    counts = {key: sum(int(s.get(key, '0')) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    if any(v < 0 for v in counts.values()) or counts['skipped'] > counts['tests']:
        raise ValueError('Invalid JUnit counts')
    if counts['tests'] <= counts['skipped'] or counts['failures'] or counts['errors']:
        raise ValueError('Tests failed, empty, or all skipped')
    return counts


def run(plan_path, out):
    plan_path = Path(plan_path).resolve()
    plan = load_plan(plan_path)
    out = Path(out).resolve()
    for root in plan['snapshot_roots']:
        if out == Path(root).resolve() or Path(root).resolve() in out.parents:
            raise ValueError('Evidence output must be outside snapshot roots')
    out.mkdir(parents=True, exist_ok=False)
    receipt = {'plan_sha256': digest(plan_path), 'snapshot': snapshot(plan['snapshot_roots']),
               'checks': [], 'passed': False}
    for check in plan['checks']:
        log = out / (check['id'] + '.log')
        junit = out / (check['id'] + '.xml')
        argv = [a.replace('{junit}', str(junit)) for a in check['argv']]
        result = {'id': check['id'], 'kind': check['kind'], 'passed': False,
                  'log': str(log), 'argv': argv}
        try:
            with log.open('wb') as stream:
                completed = subprocess.run(argv, cwd=check['cwd'], stdout=stream,
                                           stderr=subprocess.STDOUT,
                                           timeout=check.get('timeout', 120), shell=False)
            result['returncode'] = completed.returncode
            if completed.returncode != 0:
                raise ValueError('Check exited with nonzero status')
            if check['kind'] != 'format':
                result['counts'] = test_counts(junit)
                result['junit'] = str(junit)
                result['junit_sha256'] = digest(junit)
            result['passed'] = True
        except (OSError, ValueError, ET.ParseError, subprocess.TimeoutExpired) as exc:
            result['error'] = str(exc)
        result['log_sha256'] = digest(log) if log.exists() else None
        receipt['checks'].append(result)
    receipt['source_unchanged'] = (receipt['snapshot'] == snapshot(plan['snapshot_roots'])
                                   and receipt['plan_sha256'] == digest(plan_path))
    receipt['passed'] = receipt['source_unchanged'] and all(r['passed'] for r in receipt['checks'])
    (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    return receipt['passed']


def verify(plan_path, receipt_path):
    plan = load_plan(plan_path)
    receipt = json.loads(Path(receipt_path).read_text(encoding='utf-8'))
    if not receipt.get('passed') or not receipt.get('source_unchanged'):
        raise ValueError('Receipt did not pass')
    if receipt['plan_sha256'] != digest(plan_path) or receipt['snapshot'] != snapshot(plan['snapshot_roots']):
        raise ValueError('Plan or source snapshot changed')
    if len(receipt['checks']) != len(plan['checks']):
        raise ValueError('Missing required checks')
    out = Path(receipt_path).resolve().parent
    for check, result in zip(plan['checks'], receipt['checks']):
        log = out / (check['id'] + '.log')
        junit = out / (check['id'] + '.xml')
        expected_argv = [a.replace('{junit}', str(junit)) for a in check['argv']]
        if (result['id'] != check['id'] or result['kind'] != check['kind']
                or not result['passed'] or result.get('returncode') != 0
                or result['argv'] != expected_argv or result['log'] != str(log)
                or result['log_sha256'] != digest(log)):
            raise ValueError('Check evidence changed')
        if check['kind'] != 'format':
            if (result['junit'] != str(junit) or result['junit_sha256'] != digest(junit)
                    or result['counts'] != test_counts(junit)):
                raise ValueError('JUnit evidence changed')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    runner = sub.add_parser('run')
    runner.add_argument('--plan', required=True)
    runner.add_argument('--out', required=True)
    verifier = sub.add_parser('verify')
    verifier.add_argument('--plan', required=True)
    verifier.add_argument('--receipt', required=True)
    args = parser.parse_args()
    try:
        passed = run(args.plan, args.out) if args.action == 'run' else verify(args.plan, args.receipt)
        print('PASS' if passed else 'FAIL: see receipt.json')
        return 0 if passed else 1
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        print('FAIL:', exc)
        return 1


if __name__ == '__main__':
    sys.exit(main())

"""Replay Core against a private exported audit without generating new prose.

Input records are data only. Output is a new local directory; never publish it.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ids', nargs='*')
    args = p.parse_args()
    evidence = args.evidence.resolve()
    root = evidence / 'eval'
    selected = set(args.ids or [])
    records = []
    seen = set()
    # Validate every input before creating output. No source paths from JSON are used.
    for path in sorted((root / 'outputs').glob('*.json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        case_id, branch = record['case_id'], record['branch']
        if not re.fullmatch(r'[A-Z]\d{2}', case_id) or branch not in ('A', 'B'):
            raise ValueError('Invalid case or branch')
        if selected and case_id not in selected:
            continue
        key = f'{case_id}_{branch}'
        if key in seen:
            raise ValueError('Duplicate response: ' + key)
        seen.add(key)
        card = json.loads((root / 'cases' / (case_id + '.json')).read_text(encoding='utf-8'))
        original = card['fragment'].encode('utf-8')
        revision = record['final_response'].encode('utf-8')
        if sha(original) != record['input_sha256'] or sha(original) != card['input_sha256']:
            raise ValueError('Input hash mismatch: ' + key)
        if card['mode'] not in ('audit', 'rewrite', 'spoken'):
            raise ValueError('Unsupported task mode: ' + card['mode'])
        records.append((key, card, original, revision))
    if not records or selected - {key.split('_')[0] for key, *_ in records}:
        raise ValueError('Missing requested cases')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    workflow = Path(__file__).resolve().parents[1] / 'skills/slovodel/scripts/workflow.py'
    summaries = []
    for key, card, original, revision in records:
        folder = out / key
        folder.mkdir()
        before, after = folder/'before.txt', folder/'after.txt'
        before.write_bytes(original)
        after.write_bytes(revision)
        task_mode = card['mode']
        mode = 'rewrite' if task_mode == 'spoken' else task_mode
        # An audit answer is not a rewrite and must not be scored as fact preservation.
        cmd = [sys.executable, str(workflow), '--mode', mode]
        cmd += ['--input', str(before)] if mode == 'audit' else ['--before', str(before), '--after', str(after)]
        started = datetime.now(timezone.utc).isoformat()
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        (folder/'stdout.json').write_bytes(proc.stdout)
        (folder/'stderr.txt').write_bytes(proc.stderr)
        (folder/'exitcode.txt').write_text(str(proc.returncode), encoding='utf-8')
        report = json.loads(proc.stdout)
        guard = report.get('fact_guard')
        assert proc.returncode in (0, 5), key
        if guard:
            assert guard['source_sha256'] == sha(original) and guard['revision_sha256'] == sha(revision), key
        metadata = dict(case=key, mode=mode, task_mode=task_mode, started_at=started,
                        finished_at=datetime.now(timezone.utc).isoformat(), command=cmd,
                        exit_code=proc.returncode, input_sha256=sha(original), response_sha256=sha(revision),
                        execution_kind='posthoc_core_replay_no_generation',
                        platform_model=None, platform_effort=None,
                        tool_version=report['tool_version'], decision=report['decision'],
                        guard_version=guard['guard_version'] if guard else None,
                        findings=guard['findings'] if guard else [],
                        editorial_fact_verdict='not_assessed_by_replay')
        (folder/'execution.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        summaries.append(metadata)
    summary = dict(records=len(summaries), cases=len({s['case'].split('_')[0] for s in summaries}),
                   decisions=dict(Counter(s['decision'] for s in summaries)),
                   execution_kind='posthoc_core_replay_no_generation', runs=summaries)
    (out/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'}))


if __name__ == '__main__':
    main()

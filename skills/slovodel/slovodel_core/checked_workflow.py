"""Run Core and its verifier together, retaining the real subprocess exit code."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from . import __version__
from .io import DataError, emit_json, read_text
from .verification import VerificationError, verify


def word_count(text: str) -> int:
    """Whitespace-delimited lexical items including numbers; punctuation isn't a word."""
    return sum(bool(re.search(r'[^\W_]', part)) for part in text.split())


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',required=True,choices=('audit','rewrite','create','compare'))
    for flag in ('input','before','after','context-file','protected-file','reference'):
        parser.add_argument('--'+flag)
    parser.add_argument('--morphology',action='store_true')
    parser.add_argument('--require-schema',action='store_true')
    parser.add_argument('--output-dir',required=True,help='New directory; never reused or overwritten.')
    parser.add_argument('--answer',help='Final prose to check against requested word limits.')
    parser.add_argument('--min-words',type=int)
    parser.add_argument('--max-words',type=int)
    args=parser.parse_args()
    if (any(v is not None and v<0 for v in (args.min_words,args.max_words)) or
        args.min_words is not None and args.max_words is not None and args.min_words>args.max_words):
        parser.error('invalid word limits')
    bounded=args.min_words is not None or args.max_words is not None
    answer=args.answer or (args.input if args.mode=='create' else args.after if args.mode=='rewrite' else None)
    if bounded and not answer:parser.error('word limits require --answer for audit/compare')
    out=Path(args.output_dir)
    # Windows 3.13 interprets 0700 as a new owner-only DACL. In a Codex child
    # sandbox that locks the desktop user out of their own report directory.
    # Inherit the trusted workspace ACL on Windows; retain POSIX privacy.
    try:out.mkdir(mode=0o777 if os.name=='nt' else 0o700,parents=True,exist_ok=False)
    except OSError:
        print('SLOVODEL_ERROR: OUTPUT_DIRECTORY_NOT_NEW',file=sys.stderr)
        raise SystemExit(4) from None
    skill=Path(__file__).resolve().parents[1]
    command=[sys.executable,str(skill/'scripts/workflow.py'),'--mode',args.mode]
    for name in ('input','before','after','context_file','protected_file','reference'):
        value=getattr(args,name)
        if value is not None:command.extend(('--'+name.replace('_','-'),value))
    if args.morphology:command.append('--morphology')
    metadata={'execution_version':'1.0.0','tool_version':__version__,'mode':args.mode,
              'started_at':datetime.now(timezone.utc).isoformat(),
              'core_exit_code':None,'verification':'not_run','word_limits':None,
              'configured_model':None,'configured_effort':None,'publication_ready':False}
    code=6
    try:
        proc=subprocess.run(command,capture_output=True,timeout=180)
        metadata['core_exit_code']=proc.returncode
        (out/'core.stderr.txt').write_bytes(proc.stderr)
        (out/'core.json').write_bytes(proc.stdout)
        if proc.returncode not in (0,5):
            metadata['error']='CORE_EXECUTION_FAILED';code=proc.returncode
        else:
            report=json.loads(proc.stdout.decode('utf-8-sig'))
            documents={k:read_text(v)[0] for k,v in (
                ('input',args.input),('before',args.before),('after',args.after),
                ('context',args.context_file)) if v is not None}
            checked=verify(report,documents,core_exit_code=proc.returncode,
                           schema_dir=skill/'schemas',require_schema=args.require_schema)
            checked['report_sha256']=hashlib.sha256(proc.stdout).hexdigest()
            emit_json(json.dumps(checked,ensure_ascii=False,indent=2),str(out/'verification.json'))
            metadata['verification']='passed';code=proc.returncode
            if bounded:
                raw,text=read_text(answer);n=word_count(text)
                passed=(args.min_words is None or n>=args.min_words) and (args.max_words is None or n<=args.max_words)
                metadata['word_limits']={'count':n,'min':args.min_words,'max':args.max_words,
                    'answer_sha256':hashlib.sha256(raw).hexdigest(),'status':'passed' if passed else 'failed'}
                if not passed:code=7
    except (DataError,VerificationError,json.JSONDecodeError,UnicodeError,subprocess.TimeoutExpired,OSError):
        metadata['error']='CHECKED_WORKFLOW_FAILED';code=6
    metadata['finished_at']=datetime.now(timezone.utc).isoformat()
    metadata['runner_exit_code']=code
    emit_json(json.dumps(metadata,ensure_ascii=False,indent=2),str(out/'execution.json'))
    print(json.dumps({'mode':args.mode,'core_exit_code':metadata['core_exit_code'],
                      'verification':metadata['verification'],'word_limits':metadata['word_limits'],
                      'publication_ready':False},ensure_ascii=False))
    raise SystemExit(code)

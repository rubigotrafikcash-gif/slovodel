"""Verify workflow evidence without editing it or approving the prose.

The standard-library checks cover input hashes and execution invariants.
Full JSON Schema validation is optional and explicitly unavailable without
jsonschema; a subset validator is never presented as a full one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from . import __version__
from .fact_guard import VERSION as GUARD_VERSION
from .io import DataError, emit_json, read_text


class VerificationError(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError('VERIFY_DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _json(path: str) -> tuple[bytes, object]:
    raw, text = read_text(path)
    try:
        return raw, json.loads(text.lstrip('\ufeff'), object_pairs_hook=_object)
    except json.JSONDecodeError:
        raise VerificationError('VERIFY_INVALID_JSON') from None


def verify(report: dict, documents: dict[str, bytes], *, core_exit_code: int,
           schema_dir: Path, require_schema: bool = False) -> dict:
    def demand(condition, code='VERIFY_REPORT_INVALID'):
        if not condition:
            raise VerificationError(code)

    demand(isinstance(report, dict))
    mode = report.get('mode')
    demand(mode in ('audit', 'create', 'rewrite', 'compare'))
    single = mode in ('audit', 'create')
    demand(set(documents) >= ({'input'} if single else {'before', 'after'}),
           'VERIFY_INPUTS_REQUIRED')
    demand(not ({'before', 'after', 'context'} & set(documents)) if single
           else 'input' not in documents, 'VERIFY_INPUTS_INVALID')
    demand(report.get('execution') == 'local_core_executed')
    demand(report.get('tool_version') == __version__, 'VERIFY_VERSION_MISMATCH')
    demand(report.get('publication_ready') is False)
    demand(report.get('workflow_schema_version') == '1.0.0')
    decisions = {'audit': ('audit_only',), 'create': ('draft_requires_review',),
                 'rewrite': ('blocked', 'draft_requires_review'),
                 'compare': ('comparison_only',)}
    demand(report.get('decision') in decisions[mode])
    wanted_exit = 5 if report['decision'] == 'blocked' else 0
    demand(core_exit_code == wanted_exit, 'VERIFY_EXIT_CODE_MISMATCH')
    hashes = {k: hashlib.sha256(v).hexdigest() for k, v in documents.items()}
    checked_hashes = []

    def check_hash(value, key):
        demand(value == hashes[key], 'VERIFY_HASH_MISMATCH')
        checked_hashes.append(key)

    instances = [('workflow', report)]
    for field in ('pre_analysis', 'post_analysis'):
        value = report.get(field)
        required = field == ('pre_analysis' if mode == 'audit' else 'post_analysis') if single else True
        demand(isinstance(value, dict) if required else value is None)
        if required:
            demand(value.get('tool_version') == __version__, 'VERIFY_VERSION_MISMATCH')
            check_hash(value.get('source_sha256'), 'input' if single else
                       'before' if field == 'pre_analysis' else 'after')
            instances.append(('analysis', value))
    for field in ('comparison', 'fact_guard'):
        value = report.get(field)
        demand(value is None if single else isinstance(value, dict))
        if value is not None:
            demand(value.get('tool_version') == __version__, 'VERIFY_VERSION_MISMATCH')
            if field == 'comparison':
                check_hash(value.get('before', {}).get('sha256'), 'before')
                check_hash(value.get('after', {}).get('sha256'), 'after')
                instances.append(('compare', value))
            else:
                check_hash(value.get('source_sha256'), 'before')
                check_hash(value.get('revision_sha256'), 'after')
                demand(value.get('guard_version') == GUARD_VERSION, 'VERIFY_VERSION_MISMATCH')
                demand(value.get('publish_ready') is False)
                demand(value.get('semantic_equivalence') == 'not_verified')
                instances.append(('fact-guard', value))
    context = report.get('context_review')
    if context is not None:
        demand('context' in hashes and isinstance(context, dict), 'VERIFY_CONTEXT_REQUIRED')
        check_hash(context.get('context_sha256'), 'context')
    else:
        demand('context' not in hashes, 'VERIFY_CONTEXT_MISMATCH')

    # Required/allowed top-level fields are structural checks, NOT full schemas.
    schemas = []
    for name, instance in instances:
        schema = _json(str(schema_dir / (name + '.schema.json')))[1]
        demand(set(schema['required']) <= set(instance))
        demand(schema.get('additionalProperties') is not False or
               set(instance) <= set(schema['properties']))
        schemas.append((name, schema, instance))
    schema_status = 'unavailable'
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        if require_schema:
            raise VerificationError('VERIFY_SCHEMA_UNAVAILABLE') from None
    else:
        for _, schema, instance in schemas:
            try:
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(instance)
            except Exception:
                raise VerificationError('VERIFY_SCHEMA_FAILED') from None
        schema_status = 'passed'
    return {
        'verification_version': '1.0.0', 'tool_version': __version__, 'mode': mode,
        'structural_checks': 'passed', 'input_hashes': hashes,
        'hash_checks': len(checked_hashes), 'core_exit_code': core_exit_code,
        'core_decision': report['decision'], 'schema_validation': schema_status,
        'schema_instances': [n for n, _, _ in schemas],
        'schema_unavailable_reason': 'JSONSCHEMA_NOT_INSTALLED' if schema_status == 'unavailable' else None,
        'semantic_review': 'not_performed_by_verifier', 'publication_ready': False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Verify existing Core evidence, not editorial truth.')
    parser.add_argument('--report', required=True)
    parser.add_argument('--input')
    parser.add_argument('--before')
    parser.add_argument('--after')
    parser.add_argument('--context-file')
    parser.add_argument('--core-exit-code', type=int, choices=(0, 5), required=True)
    parser.add_argument('--require-schema', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        raw, report = _json(args.report)
        documents = {name: read_text(path)[0] for name, path in (
            ('input', args.input), ('before', args.before), ('after', args.after),
            ('context', args.context_file)) if path is not None}
        result = verify(report, documents, core_exit_code=args.core_exit_code,
                        schema_dir=Path(__file__).resolve().parents[1] / 'schemas',
                        require_schema=args.require_schema)
        result['report_sha256'] = hashlib.sha256(raw).hexdigest()
        emit_json(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), args.output)
    except (DataError, VerificationError) as error:
        print('SLOVODEL_ERROR: ' + str(error), file=sys.stderr)
        raise SystemExit(6) from None
    except (ValueError, TypeError, KeyError, AttributeError):
        print('SLOVODEL_ERROR: VERIFY_REPORT_INVALID', file=sys.stderr)
        raise SystemExit(6) from None


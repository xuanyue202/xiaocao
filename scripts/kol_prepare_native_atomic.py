#!/usr/bin/env python3
"""Prepare a one-dispatch CUA plan; this command performs no UI or capture action."""
import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def versioned_runtime_url(runtime: Path, controller: Path) -> str:
    """Avoid reusing an older runtime in the persistent CUA module cache."""
    module_hash = hashlib.sha256(runtime.read_bytes()+controller.read_bytes()).hexdigest()
    return runtime.as_uri()+"?source="+module_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', required=True)
    parser.add_argument('--capture-job-id', required=True)
    parser.add_argument('--browser-proof', type=Path, required=True)
    parser.add_argument('--entry-proof', type=Path, required=True)
    parser.add_argument('--readiness-proof', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('capture', 'diagnostic'), default='capture')
    parser.add_argument('--diagnostic-authorization-sha256')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root/'output/live/kol_xiaocao_live/wechat_subscription/manifest.json').read_text())
    item = manifest['items'][args.identity]
    if item.get('capture_job_id') != args.capture_job_id:
        parser.error('original capture binding changed')
    if args.mode == 'diagnostic' and not args.diagnostic_authorization_sha256:
        parser.error('UI diagnostic requires current human authorization binding')
    if args.mode == 'capture' and item.get('status') == 'completed':
        parser.error('completed capture cannot be activated')
    source = root/'scripts/kol_vision_ocr.swift'
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    binary = root/'output/live/kol_native_atomic'/f'vision-{source_sha[:16]}'
    binary.parent.mkdir(parents=True, exist_ok=True)
    if not binary.exists():
        subprocess.run(['swiftc', '-O', str(source), '-o', str(binary)], check=True,
                       capture_output=True, timeout=45)
    browser = json.loads(args.browser_proof.read_text())
    plan = dict(schema_version=1, mode=args.mode, repo_root=str(root),
        identity=args.identity, capture_job_id=args.capture_job_id,
        message_sha256=item['message_sha256'], saved_target=browser['saved_target'],
        browser_proof_path=str(args.browser_proof.resolve()),
        entry_proof_path=str(args.entry_proof.resolve()),
        readiness=json.loads(args.readiness_proof.read_text()),
        vision_binary=str(binary), vision_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        prepared_at=datetime.now(timezone.utc).isoformat())
    if args.mode == 'diagnostic':
        plan['explicit_ui_diagnostic_authorization_sha256'] = args.diagnostic_authorization_sha256
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    runtime = root/'scripts/kol_native_course_runtime.mjs'
    controller = root/'scripts/kol_native_course_allow.mjs'
    snippet = ('// KOL_ACTION:OPEN_ALLOW_ATOMIC\n'
        f'var kolAtomicModule = await import({json.dumps(versioned_runtime_url(runtime, controller))});\n'
        f'var kolAtomicResult = await kolAtomicModule.runAtomicCourseAllow({{app:wechat,planPath:{json.dumps(str(args.output.resolve()))},emit:row=>nodeRepl.write(row)}});\n'
        'nodeRepl.write(kolAtomicResult);')
    print(json.dumps({'plan_path': str(args.output.resolve()), 'cua_snippet': snippet}, ensure_ascii=False))


if __name__ == '__main__':
    main()

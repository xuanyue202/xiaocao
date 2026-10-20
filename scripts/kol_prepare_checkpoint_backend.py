#!/usr/bin/env python3
"""Build the reviewed backend repair; installation is a separate cleanup gate."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--backend-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    backend=args.backend_root.expanduser().resolve()
    output=args.output.expanduser().resolve()
    if output.parent!=backend or output.name=='wx_video_download_macos_arm64':
        parser.error('build output must be a separate same-directory candidate, never the installed binary')
    resources=Path(__file__).resolve().parent/'kol_backend_patches'
    bindings=json.loads((resources/'integration_bindings.json').read_text())
    states=[]
    for item in bindings:
        actual=sha(backend/item['path'])
        if actual not in {item['before_sha256'],item['after_sha256']}:
            raise RuntimeError('backend source drift: '+item['path'])
        states.append(actual==item['after_sha256'])
    if any(states) and not all(states):
        raise RuntimeError('partially applied backend integration requires diagnosis')
    copies={
        'replay_cache.go':'pkg/gopeed/internal/protocol/stream/replay_cache.go',
        'replay_cache_test.go':'pkg/gopeed/internal/protocol/stream/replay_cache_test.go',
        'replay_ffmpeg_test.go':'pkg/gopeed/internal/protocol/stream/replay_ffmpeg_test.go',
        'repair_stream.go':'pkg/gopeed/pkg/download/repair_stream.go',
        'repair_stream_test.go':'pkg/gopeed/pkg/download/repair_stream_test.go',
        'repair_stream_handler.go':'internal/api/repair_stream_handler.go',
    }
    for source,relative in copies.items():
        target=backend/relative
        if target.exists() and sha(target)!=sha(resources/source):
            raise RuntimeError('additive backend source drift: '+relative)
    for source,relative in copies.items():
        target=backend/relative
        if not target.exists():target.write_bytes((resources/source).read_bytes())
    if not all(states):
        subprocess.run(['git','-C',str(backend),'apply','--check',str(resources/'integration.patch')],check=True)
        subprocess.run(['git','-C',str(backend),'apply',str(resources/'integration.patch')],check=True)
    for item in bindings:
        if sha(backend/item['path'])!=item['after_sha256']:raise RuntimeError('backend integration hash mismatch')
    subprocess.run(['go','test','./internal/protocol/stream','./pkg/download','-count=1'],cwd=backend/'pkg/gopeed',check=True)
    subprocess.run(['go','test','./internal/api','./internal/interceptor','-count=1'],cwd=backend,check=True)
    subprocess.run(['go','build','-trimpath','-o',str(output),'.'],cwd=backend,check=True)
    print(json.dumps({'status':'prepared_only','binary':str(output),'sha256':sha(output),
                      'integration':bindings,'installed':False},ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())

#!/usr/bin/env python3
"""生成自动更新的 latest.json

作为 release 资产发布到 releases/latest/download/latest.json：客户端取它不需要
带鉴权的 REST API，也就绕开了匿名调用限流（本机出口 IP 常被限到 60 次/小时）。

用法（CI 里）：
    python tools/make_update_manifest.py --dir dist --tag "$GITHUB_REF_NAME" \
        --out dist/latest.json --notes-file notes.md --published-at 2026-09-26T00:00:00Z
"""
import argparse
import hashlib
import json
import os
import sys

REPO = 'zisull/CardRead2'

# 键名必须与 src/core/updater.py 的 platform_key() 返回值一致
PACKAGES = {
    'windows-x64': 'CardRead2-Windows-x64.zip',
    'linux-x64': 'CardRead2-Linux-x64.tar.gz',
    'macos-x64': 'CardRead2-macOS-x64.zip',
    'macos-arm64': 'CardRead2-macOS-arm64.zip',
}

NOTES_LIMIT = 4000


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(tag: str, asset_dir: str, notes: str, published_at: str) -> dict:
    assets = {}
    for key, name in PACKAGES.items():
        path = os.path.join(asset_dir, name)
        if not os.path.isfile(path):
            print('::warning::缺少产物 %s（%s），该平台本次不可自动更新' % (name, key))
            continue
        assets[key] = {
            'url': 'https://github.com/%s/releases/download/%s/%s' % (REPO, tag, name),
            'sha256': sha256_of(path),
            'size': os.path.getsize(path),
        }
    return {
        'version': tag,
        'notes': notes[:NOTES_LIMIT],
        'published_at': published_at,
        'enabled': bool(assets),
        'assets': assets,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True, help='已下载产物的目录')
    ap.add_argument('--tag', required=True, help='release tag，如 v0.0.5')
    ap.add_argument('--out', required=True, help='latest.json 输出路径')
    ap.add_argument('--notes-file', help='更新说明文本文件（通常取 release body）')
    ap.add_argument('--published-at', default='')
    args = ap.parse_args()

    if not args.tag.startswith('v'):
        print('::error::tag 形如 v0.0.5，收到 %s' % args.tag)
        return 2

    notes = ''
    if args.notes_file and os.path.isfile(args.notes_file):
        with open(args.notes_file, 'r', encoding='utf-8', errors='replace') as f:
            notes = f.read().strip()

    manifest = build_manifest(args.tag, args.dir, notes, args.published_at)
    if not manifest['assets']:
        print('::error::没有任何产物可写入 manifest，跳过发布')
        return 1

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print('latest.json: version=%s platforms=%s' %
          (manifest['version'], ', '.join(sorted(manifest['assets']))))
    return 0


if __name__ == '__main__':
    sys.exit(main())

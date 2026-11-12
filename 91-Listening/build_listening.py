#!/usr/bin/env python3
"""独立生成听音默写；只读取已存在的日常词表，不推进学习游标。"""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parent.parent / '90-ReviewApp'
sys.path.insert(0, str(SOURCE))
from build_review import load_config
from listening_project import write_listening_project
from word_audio import build_audio_map, finish_audio_build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default=date.today().isoformat(), help='已生成的词表日期')
    parser.add_argument('--offline', action='store_true', help='不请求近义词扩展；音频使用现有缓存')
    args = parser.parse_args()
    study_date = date.fromisoformat(args.date)
    files = sorted((SOURCE / 'sync').rglob(f'day_{args.date}.json'))
    if not files:
        parser.error('未找到该日期的日常词表；请先生成日常词表。')
    words = json.loads(files[-1].read_text())
    config = load_config()
    if args.offline:
        import re
        # 只读本地缓存，不因缺音频而请求外部服务。
        from word_audio import cache_key
        try:
            cache = json.loads((SOURCE / '.audio_cache/index.json').read_text())
        except (OSError, ValueError):
            cache = {}
        audio = {}
        for w in words:
            key = cache_key(w, config)
            e = cache.get(key, {})
            if e.get('file') == key + '.mp3' and (SOURCE / '.audio_cache' / e['file']).is_file():
                audio[w['word']] = {'src': '.audio_cache/' + e['file']}
    else:
        audio = build_audio_map(words, config)
    write_listening_project(words, audio, study_date, config, offline=args.offline)
    if not args.offline:
        finish_audio_build(audio, config)


if __name__ == '__main__':
    main()

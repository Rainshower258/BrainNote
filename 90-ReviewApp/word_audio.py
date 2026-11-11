#!/usr/bin/env python3
"""构建期准备英文单词音频；词典优先、MiMo 补缺，音频只存本机。"""

import base64
import concurrent.futures
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request

APP_DIR = Path(__file__).resolve().parent
MAX_RESPONSE = 2 * 1024 * 1024
POS = {'n': 'noun', 'v': 'verb', 'vt': 'verb', 'vi': 'verb',
       'adj': 'adjective', 'a': 'adjective', 'ad': 'adverb', 'adv': 'adverb'}
USER_AGENT = 'Mozilla/5.0'


def primary_pos(word):
    """词卡首义项的词性；同形异音词按首义项选音。"""
    meaning = re.split(r'\s+/\s+', word.get('meaning', ''))[0]
    match = re.search(r'(?:^|[（(\s])(adj|adv|vt|vi|n|v|a|ad)\.', meaning)
    return POS.get(match.group(1), '') if match else ''


def primary_ipa(word):
    ipa = word.get('phonetic', '').strip().strip('/')
    return re.split(r'[;,；]|\(for ', ipa)[0].strip()


def normalized_ipa(ipa):
    return unicodedata.normalize('NFC', ipa).strip('/[] ').replace("'", 'ˈ').replace('ː', '').replace('.', '')


def cache_key(word, config):
    identity = [4, word['word'].lower(), primary_pos(word), primary_ipa(word),
                config.get('mimo_tts_model', 'mimo-v2.5-tts'), config.get('mimo_tts_voice', 'Mia')]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:24]


def request_bytes(url, timeout=15, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = response.read(MAX_RESPONSE + 1)
    if len(result) > MAX_RESPONSE:
        raise ValueError('audio response too large')
    return result


def dictionary_candidates(word, entries):
    """只接受精确词条；多读音时必须匹配音标，避免错用另一词性的读音。"""
    target = normalized_ipa(primary_ipa(word))
    pos = primary_pos(word)
    candidates = []
    for entry in entries:
        if entry.get('word', '').casefold() != word['word'].casefold():
            continue
        senses = {m.get('partOfSpeech') for m in entry.get('meanings', [])}
        if pos and pos not in senses:
            continue
        for phonetic in entry.get('phonetics', []):
            url = phonetic.get('audio', '')
            if url.startswith('//'):
                url = 'https:' + url
            if urllib.parse.urlparse(url).scheme != 'https':
                continue
            candidates.append({'url': url, 'ipa': phonetic.get('text', ''),
                               'source': 'dictionary', 'source_page': phonetic.get('sourceUrl', ''),
                               'license': phonetic.get('license', {})})
    exact = [c for c in candidates if target and normalized_ipa(c['ipa']) == target]
    if exact:
        candidates = exact
    elif len({normalized_ipa(c['ipa']) for c in candidates if c['ipa']}) > 1:
        # The entry exposes distinct pronunciations without a reliable sense/IPA match.
        return []
    # 英美均可；相同音标优先美音。保留备用 URL，应对某个音频失效。
    return sorted(candidates, key=lambda c: ('-us.' not in c['url'] and '_us_' not in c['url']))


def get_dictionary(word):
    url = 'https://api.dictionaryapi.dev/api/v2/entries/en/' + urllib.parse.quote(word['word'], safe='')
    entries = json.loads(request_bytes(url))
    if not isinstance(entries, list):
        return []
    return dictionary_candidates(word, entries)


def cambridge_candidates(word, page):
    """按 Cambridge 完整词条块的词头/词性取音，不误取例句或相关词。"""
    result = []
    blocks = re.split(r'<div[^>]+class="[^"]*\bentry-body__el\b[^"]*"[^>]*>', page)[1:]
    for block in blocks:
        headword = re.search(r'<span class="hw dhw">(.*?)</span>', block, re.S)
        pos = re.search(r'<span class="pos dpos"[^>]*>(.*?)</span>', block, re.S)
        clean = lambda s: html.unescape(re.sub(r'<[^>]+>', '', s)).strip()
        if not headword or clean(headword.group(1)).casefold() != word['word'].casefold():
            continue
        wanted_pos = primary_pos(word)
        if wanted_pos and (not pos or clean(pos.group(1)) != wanted_pos):
            continue
        regions = re.split(r'<span class="(?:uk|us) dpron-i[^"\n]*">', block)[1:3]
        for region in regions:
            source = re.search(r'<source type="audio/mpeg" src="([^"]+)"', region)
            ipa = re.search(r'<span class="ipa [^"]*">(.*?)</span>', region, re.S)
            if source and ipa:
                result.append({'url': urllib.parse.urljoin('https://dictionary.cambridge.org', html.unescape(source.group(1))),
                               'ipa': clean(ipa.group(1)), 'source': 'cambridge',
                               'source_page': 'https://dictionary.cambridge.org/dictionary/english/' + urllib.parse.quote(word['word'])})
        # 首个匹配主词性词条已有读音，无须采集商务/美式词典等重复词条。
        if result:
            break
    return result


def get_cambridge(word):
    url = 'https://dictionary.cambridge.org/dictionary/english/' + urllib.parse.quote(word['word'], safe='')
    return cambridge_candidates(word, request_bytes(url).decode('utf-8'))


def get_mimo(word, config):
    key = config.get('mimo_api_key') or os.environ.get('MIMO_API_KEY')
    if not key:
        return None
    pos = primary_pos(word)
    ipa = primary_ipa(word)
    instruction = ('Pronounce only the single English headword provided, once, clearly in a standard '
                   'British or American accent, at a natural dictionary pace. No introduction, '
                   'spelling letters, translation, explanation, music or extra words.')
    if pos:
        instruction += ' Use its ' + pos + ' pronunciation.'
    if ipa:
        instruction += ' The word card gives this pronunciation as a reference: /' + ipa + '/.'
    body = {'model': config.get('mimo_tts_model', 'mimo-v2.5-tts'),
            'messages': [{'role': 'user', 'content': instruction},
                         {'role': 'assistant', 'content': word['word']}],
            'audio': {'format': 'mp3', 'voice': config.get('mimo_tts_voice', 'Mia')},
            'stream': False}
    # 不接受任意 base_url，防止本地误配置把凭据发给其他服务。
    data = request_bytes('https://api.xiaomimimo.com/v1/chat/completions',
                         timeout=30, data=json.dumps(body).encode(),
                         headers={'api-key': key, 'Content-Type': 'application/json'})
    response = json.loads(data)
    raw = base64.b64decode(response['choices'][0]['message']['audio']['data'], validate=True)
    return raw, {'source': 'mimo', 'ipa': ipa, 'voice': body['audio']['voice'], 'model': body['model']}


def encode_mp3(raw, destination):
    """解码校验后压成 24 kHz / 单声道 / 32 kbps；不裁剪辅音或尾音。"""
    with tempfile.TemporaryDirectory(prefix='convert-', dir=destination.parent) as tmp:
        original, encoded = Path(tmp) / 'input.audio', Path(tmp) / 'output.mp3'
        original.write_bytes(raw)
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(original),
                        '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '24000', '-c:a', 'libmp3lame',
                        '-b:a', '32k', '-map_metadata', '-1', str(encoded)],
                       check=True, capture_output=True, timeout=15)
        info = json.loads(subprocess.check_output(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(encoded)],
            timeout=5))
        duration = float(info['format']['duration'])
        if not 0.15 <= duration <= 6:
            raise ValueError('unexpected single-word audio duration')
        os.replace(encoded, destination)
    return duration


def prepare_word(word, config, directory, key):
    target = directory / (key + '.mp3')
    for provider in (get_cambridge, get_dictionary):
        try:
            candidates = provider(word)
        except Exception:
            candidates = []
        for candidate in candidates:
            try:
                duration = encode_mp3(request_bytes(candidate['url']), target)
                return {**candidate, 'file': target.name, 'duration': duration}
            except Exception:
                continue
    try:
        result = get_mimo(word, config)
        if result:
            raw, metadata = result
            duration = encode_mp3(raw, target)
            return {**metadata, 'file': target.name, 'duration': duration}
    except Exception as exc:
        # 不打印异常正文：HTTP 错误/第三方响应可能包含私有信息。
        print(f"  [audio] {word['word']}：MiMo 不可用（{type(exc).__name__}），本次跳过读音")
    return None


def prune_cache(directory, entries, pinned, max_bytes):
    """按文件真实大小淘汰最久未用音频；当日词表引用永不删除。"""
    for key in list(entries):
        filename = entries[key].get('file', '')
        if filename != key + '.mp3' or not (directory / filename).is_file():
            entries.pop(key)
    tracked = {e['file'] for e in entries.values()}
    for path in directory.glob('*.mp3'):
        if path.name not in tracked:
            path.unlink()
    size = sum((directory / e['file']).stat().st_size for e in entries.values())
    for key in sorted(entries, key=lambda k: entries[k].get('last_used', 0)):
        if size <= max_bytes:
            break
        if key in pinned:
            continue
        path = directory / entries[key]['file']
        size -= path.stat().st_size
        path.unlink()
        del entries[key]
    return size


def build_audio_map(words, config, use_mock=False, app_dir=APP_DIR):
    if use_mock or not config.get('audio_enabled', True):
        return {}
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        print('[audio] 缺少 ffmpeg/ffprobe，跳过音频构建')
        return {}
    directory = Path(app_dir) / '.audio_cache'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('[audio] 另一构建正在准备音频，本次跳过')
            return {}
        return _build_audio_map(words, config, directory)


def _build_audio_map(words, config, directory):
    index = directory / 'index.json'
    try:
        entries = json.loads(index.read_text())
        if not isinstance(entries, dict):
            entries = {}
    except (OSError, ValueError):
        entries = {}
    now = time.time()
    keyed = {cache_key(w, config): w for w in words}
    missing = {}
    for key, word in keyed.items():
        entry = entries.get(key, {})
        if entry.get('file') == key + '.mp3' and (directory / entry['file']).is_file():
            entry['last_used'] = now
        else:
            entries.pop(key, None)
            missing[key] = word
    print(f'[audio] 缓存命中 {len(keyed) - len(missing)}/{len(keyed)}，准备缺失音频 {len(missing)}')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(prepare_word, w, config, directory, k): (k, w) for k, w in missing.items()}
        for job in concurrent.futures.as_completed(jobs):
            key, word = jobs[job]
            try:
                entry = job.result()
            except Exception:
                entry = None
            if entry:
                entries[key] = {**entry, 'word': word['word'], 'pos': primary_pos(word),
                                'created': now, 'last_used': now}
                print(f"  [audio] {word['word']} ✓（{entry['source']}）")
            else:
                print(f"  [audio] {word['word']}：暂无可用读音，不影响背词")
    # 清理必须在页面成功落盘之后完成，调用方显式调用 finish_audio_build。
    temp = index.with_suffix('.tmp')
    temp.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n')
    os.replace(temp, index)
    return {word['word']: {'src': '.audio_cache/' + entries[key]['file'],
                           'source': entries[key]['source'], 'ipa': entries[key].get('ipa', '')}
            for key, word in keyed.items() if key in entries}


def finish_audio_build(audio_map, config, app_dir=APP_DIR):
    directory = Path(app_dir) / '.audio_cache'
    index = directory / 'index.json'
    if not index.exists():
        return
    with (directory / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = json.loads(index.read_text())
        pinned = {Path(e['src']).stem for e in audio_map.values()}
        limit = max(1, float(config.get('audio_cache_max_mb', 100))) * 1024 * 1024
        size = prune_cache(directory, entries, pinned, limit)
        temp = index.with_suffix('.tmp')
        temp.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n')
        os.replace(temp, index)
        print(f'[audio] 本地缓存 {size / 1024 / 1024:.2f} MB / {limit / 1024 / 1024:.0f} MB')

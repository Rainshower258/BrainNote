"""从当日词表构建独立听音默写项目；不修改普通背词成绩。"""
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent / '91-Listening'


def meaning_key(word):
    return hashlib.sha256((word['word'] + '\n' + word['meaning']).encode()).hexdigest()[:24]


def basic_aliases(meaning):
    text = re.sub(r'[（(][^）)]*[）)]|\[[^\]]*\]', '', meaning)
    text = re.sub(r'\b[a-z&]+\.', '', text)
    result = []
    for part in re.split(r'[/,，;；、\n]', text):
        part = re.sub(r'[…·.\s]+', '', part).strip('：:')
        if part and re.search(r'[\u3400-\u9fff]', part):
            result.append(part)
    return list(dict.fromkeys(result))


def generate_aliases(words, config):
    """只在构建时补充近义说法；答题不联网。失败时使用原词义。"""
    key = config.get('deepseek_api_key', '')
    if not words or not key:
        return {}
    prompt = ('为英语听写练习整理宽松的中文答案。根据给定词义，为每词给出8-20个常用中文同义、近义或简短释义。'
              '任意一个正确义项即可，不要求完整列出全部词义。只覆盖给定义项，不加入反义词、不遗漏否定或因果。'
              '每项1-16个汉字，可带“的”，不要词性、英语、解释或例句。只返回JSON对象，键为原英文词，值为字符串数组。\n'
              + json.dumps({w['word']: w['meaning'] for w in words}, ensure_ascii=False))
    body = {'model': config.get('model', 'deepseek-v4-flash'),
            'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.2,
            'response_format': {'type': 'json_object'}}
    url = config.get('base_url', 'https://api.deepseek.com').rstrip('/') + '/chat/completions'
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            obj = json.load(resp)
        result = json.loads(obj['choices'][0]['message']['content'])
        return {w['word']: [s.strip() for s in result.get(w['word'], [])
                            if isinstance(s, str) and re.fullmatch(r'[\u3400-\u9fff]{1,16}', s.strip())][:24]
                for w in words if isinstance(result.get(w['word']), list)}
    except Exception as exc:
        print(f'[listening] 近义词扩展暂不可用（{type(exc).__name__}），保留原释义判定')
        return {}


def build_alias_map(words, config, project_dir=PROJECT_DIR, offline=False):
    project_dir = Path(project_dir)
    cache_path = project_dir / 'aliases_cache.json'
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cache = {}
    try:
        curated = json.loads((project_dir / 'aliases.json').read_text())
    except (OSError, ValueError):
        curated = {}
    missing = [w for w in words if meaning_key(w) not in cache and w['word'] not in curated]
    generated = {} if offline else generate_aliases(missing, config)
    for word in missing:
        values = generated.get(word['word'])
        if values:
            cache[meaning_key(word)] = {'word': word['word'], 'meaning': word['meaning'], 'accepted': values}
    result = {}
    for word in words:
        extra = curated.get(word['word'], [])
        result[word['word']] = list(dict.fromkeys(basic_aliases(word['meaning']) + extra
                                    + cache.get(meaning_key(word), {}).get('accepted', [])))
    if generated:
        project_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + '\n')
    return result


def write_listening_project(words, audio_map, study_date, config, project_dir=PROJECT_DIR, offline=False):
    project_dir = Path(project_dir).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    aliases = build_alias_map(words, config, project_dir, offline)
    # day JSON 和导出 session 都带独立项目类型，不作为普通背词成绩同步。
    data = {'kind': 'listening', 'date': study_date.isoformat(), 'words': []}
    for word in words:
        sound = audio_map.get(word['word'], {})
        src = sound.get('src', '')
        if src:
            src = os.path.relpath(APP_DIR / src, project_dir)
        data['words'].append({'id': word['word'], 'word': word['word'], 'meaning': word['meaning'],
                              'acceptedZh': aliases[word['word']], 'audio': src})
    template = (project_dir / 'template.html').read_text()
    page = template.replace('@@DATA@@', json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))
    page = page.replace('@@MATCHER@@', (project_dir / 'answer_matcher.js').read_text())
    (project_dir / 'listening.html').write_text(page)
    days = project_dir / 'days'
    days.mkdir(exist_ok=True)
    (days / f'day_{study_date.isoformat()}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(f'[listening] 独立听音默写 {len(words)} 词，已写 {project_dir / "listening.html"}')
    return data

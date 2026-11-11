import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import word_audio as audio


class WordAudioTests(unittest.TestCase):
    def test_first_sense_pos_and_pronunciation_have_separate_cache_keys(self):
        adjective = {'word': 'appropriate', 'meaning': '适当的 (adj.) / 挪用 (vt.)', 'phonetic': '/əˈprəʊpriət; for v. əˈprəʊprieɪt/'}
        verb = {**adjective, 'meaning': '挪用 (vt.)', 'phonetic': '/əˈprəʊprieɪt/'}
        self.assertEqual(audio.primary_pos(adjective), 'adjective')
        self.assertEqual(audio.primary_ipa(adjective), 'əˈprəʊpriət')
        self.assertNotEqual(audio.cache_key(adjective, {}), audio.cache_key(verb, {}))

    def test_dictionary_does_not_use_noun_record_audio_for_verb(self):
        word = {'word': 'record', 'meaning': '记录 (v.)', 'phonetic': '/rɪˈkɔːd/'}
        entries = [{'word': 'record', 'meanings': [{'partOfSpeech': 'noun'}], 'phonetics': [
            {'text': '/ˈrekɔːd/', 'audio': 'https://example.org/record-noun.mp3'}]}]
        self.assertEqual(audio.dictionary_candidates(word, entries), [])
        entries[0]['meanings'][0]['partOfSpeech'] = 'verb'
        entries[0]['phonetics'].append({'text': '/rɪˈkɔːd/', 'audio': 'https://example.org/record-verb.mp3'})
        self.assertEqual([c['url'] for c in audio.dictionary_candidates(word, entries)], ['https://example.org/record-verb.mp3'])

    def test_cambridge_matches_headword_pos_and_audio_region(self):
        page = '''<div class="pr entry-body__el"><span class="hw dhw">record</span><span class="pos dpos">noun</span>
        <span class="uk dpron-i "><source type="audio/mpeg" src="/noun.mp3"><span class="ipa dipa">ˈrek.ɔːd</span></span>
        <div class="pr entry-body__el"><span class="hw dhw">record</span><span class="pos dpos">verb</span>
        <span class="uk dpron-i "><source type="audio/mpeg" src="/verb.mp3"><span class="ipa dipa">rɪˈkɔːd</span></span>'''
        result = audio.cambridge_candidates({'word': 'record', 'meaning': '记录 (v.)'}, page)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['url'].endswith('/verb.mp3'))
        self.assertEqual(result[0]['ipa'], 'rɪˈkɔːd')

    def test_cache_reuses_audio_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            word = {'word': 'cute', 'meaning': '可爱的 (adj.)', 'phonetic': '/kjuːt/'}
            cache = Path(tmp) / '.audio_cache'
            cache.mkdir()
            key = audio.cache_key(word, {})
            (cache / (key + '.mp3')).write_bytes(b'cached')
            (cache / 'index.json').write_text(json.dumps({key: {'file': key + '.mp3', 'source': 'cambridge'}}))
            with patch.object(audio, 'prepare_word', side_effect=AssertionError('should not fetch')):
                result = audio.build_audio_map([word, word], {}, app_dir=Path(tmp))
            self.assertEqual(list(result), ['cute'])
            self.assertEqual(result['cute']['src'], '.audio_cache/' + key + '.mp3')

    def test_cache_prunes_oldest_but_preserves_current_and_deletes_orphans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = {}
            for key, used in [('old', 1), ('current', 0), ('recent', 3)]:
                (root / (key + '.mp3')).write_bytes(b'x' * 40)
                entries[key] = {'file': key + '.mp3', 'last_used': used}
            (root / 'orphan.mp3').write_bytes(b'x' * 80)
            size = audio.prune_cache(root, entries, {'current'}, 80)
            self.assertEqual(size, 80)
            self.assertEqual(set(entries), {'current', 'recent'})
            self.assertFalse((root / 'old.mp3').exists())
            self.assertFalse((root / 'orphan.mp3').exists())

    def test_dictionary_failure_uses_mimo_and_no_failed_audio_file_is_kept(self):
        word = {'word': 'cute', 'meaning': '可爱的 (adj.)'}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(audio, 'get_cambridge', side_effect=OSError), patch.object(audio, 'get_dictionary', return_value=[]), patch.object(audio, 'get_mimo', return_value=(b'sample', {'source': 'mimo'})), patch.object(audio, 'encode_mp3', return_value=1.2):
                self.assertEqual(audio.prepare_word(word, {}, Path(tmp), 'abc')['source'], 'mimo')
            with patch.object(audio, 'get_cambridge', return_value=[]), patch.object(audio, 'get_dictionary', return_value=[]), patch.object(audio, 'get_mimo', return_value=None):
                self.assertIsNone(audio.prepare_word(word, {}, Path(tmp), 'abc'))

    def test_mock_is_offline_and_does_not_create_audio_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(audio.build_audio_map([{'word': 'cute'}], {}, use_mock=True, app_dir=Path(tmp)), {})
            self.assertFalse((Path(tmp) / '.audio_cache').exists())

    def test_html_error_response_is_rejected_by_decoder(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'bad.mp3'
            with self.assertRaises(Exception):
                audio.encode_mp3(b'<html>Gateway error</html>', target)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()

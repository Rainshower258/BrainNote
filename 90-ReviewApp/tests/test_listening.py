from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import listening_project as project


class ListeningTests(unittest.TestCase):
    def test_original_meanings_preserved_and_model_failure_still_has_answers(self):
        word={'word':'deficiency','meaning':'缺乏，不足；缺点，缺陷 (n.)'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(project,'generate_aliases',return_value={}):
            values=project.build_alias_map([word],{},Path(tmp))['deficiency']
            self.assertEqual(values,['缺乏','不足','缺点','缺陷'])

    def test_meaning_change_invalidates_generated_alias_cache(self):
        a={'word':'record','meaning':'记录 (v.)'}
        self.assertNotEqual(project.meaning_key(a),project.meaning_key({**a,'meaning':'唱片 (n.)'}))

    def test_build_independent_project_uses_local_audio_and_no_progress_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'template.html').write_text('<script>const DATA=@@DATA@@;@@MATCHER@@</script>')
            (p/'answer_matcher.js').write_text('// offline matcher')
            (p/'aliases.json').write_text(json.dumps({'cute':['萌','可爱']}))
            progress=project.APP_DIR/'progress.json';before=progress.read_bytes()
            with patch.object(project,'generate_aliases',side_effect=AssertionError('must be offline')):
                data=project.write_listening_project([{'word':'cute','meaning':'可爱的 (adj.)'}],{'cute':{'src':'.audio_cache/example.mp3'}},date(2026,11,12),{},p,offline=True)
            self.assertEqual(data['kind'],'listening')
            self.assertIn('萌',data['words'][0]['acceptedZh'])
            self.assertEqual((p/data['words'][0]['audio']).resolve(),(project.APP_DIR/'.audio_cache/example.mp3').resolve())
            self.assertEqual(progress.read_bytes(),before)
            self.assertTrue((p/'days/day_2026-11-12.json').exists())

    def test_listening_export_is_rejected_by_normal_sync(self):
        progress=project.APP_DIR/'progress.json';before=progress.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'listening_session.json'
            path.write_text(json.dumps({'kind':'listening','date':'2026-11-12','attempts':[]}))
            result=subprocess.run([sys.executable,str(project.APP_DIR/'sync_session.py'),'--file',str(path)],capture_output=True,text=True,check=True)
            self.assertIn('独立项目',result.stdout)
            self.assertEqual(progress.read_bytes(),before)

if __name__=='__main__':unittest.main()

"""A stale loop must not be accepted merely because a participant JSON exists."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
import unittest
from podcast_automation.transcritorWhisper import TranscritorWhisper
class CacheTests(unittest.TestCase):
    def run_cache(self,rows,healthy):
        with TemporaryDirectory() as temporary:
            file=Path(temporary)/'participant.json';file.write_text(json.dumps(rows))
            transcriber=TranscritorWhisper.__new__(TranscritorWhisper);transcriber.cache_rebuilt=False
            transcriber.grupos_transcricao={'Kojiro':['original.flac']};transcriber.json_paths={'Kojiro':str(file)}
            transcriber.carregar_modelo=Mock(side_effect=RuntimeError('pending-retranscription'))
            if healthy:
                transcriber.processar_participantes();transcriber.carregar_modelo.assert_not_called()
                self.assertFalse(transcriber.cache_rebuilt)
            else:
                with self.assertRaisesRegex(RuntimeError,'pending-retranscription'):transcriber.processar_participantes()
                self.assertTrue(transcriber.cache_rebuilt)
                self.assertEqual(json.loads(file.read_text()),rows)
    def test_healthy_and_silent_caches_reused(self):
        self.run_cache([{'inicio':0,'fim':2,'texto':'Uma fala normal.'}],True);self.run_cache([],True)
    def test_repeated_and_invalid_cache_retranscribed_without_early_deletion(self):
        self.run_cache([{'inicio':0,'fim':20,'texto':'tá '*6}],False)
        self.run_cache([{'inicio':0,'fim':20,'texto':'aham'} for _ in range(6)],False)
        self.run_cache([{'texto':'sem timestamps'}],False)
if __name__=='__main__':unittest.main()

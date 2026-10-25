import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    'pia_stt', Path(__file__).resolve().parents[1] / 'src/podcast_automation/piaTranscription.py'
)
stt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stt)


class PiaTranscriptionTests(unittest.TestCase):
    def setUp(self):
        context=dict(url='http://localhost:8762',model='pia-default',max_upload_bytes=209715200,token='internal-fixture')
        first=patch.object(stt,'current',return_value=context);first.start();self.addCleanup(first.stop)
        second=patch('src.app_access.current',return_value=context);second.start();self.addCleanup(second.stop)

    def response(self, **changes):
        data = {'duration': 105.0, 'text': 'Primeira. Segunda.', 'segments': [
            {'id': 0, 'start': 2.25, 'end': 3.5, 'text': 'Primeira.'},
            {'id': 1, 'start': 93.1, 'end': 94.2, 'text': 'Segunda.'},
        ]}
        data.update(changes)
        return data

    @patch.dict(os.environ, {}, clear=True)
    def test_whole_file_upload_auth_and_timestamps(self):
        response = Mock(status_code=200, json=Mock(return_value=self.response()))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'participante.ogg'
            path.write_bytes(b'whole audio')

            def post(url, **kwargs):
                self.assertEqual(url, 'http://localhost:8762/v1/audio/transcriptions')
                self.assertNotIn('Authorization',kwargs['headers'])
                self.assertEqual(kwargs['headers']['X-PIA-App-Token'],'internal-fixture')
                self.assertEqual(kwargs['data']['response_format'], 'verbose_json')
                self.assertEqual(kwargs['files']['file'][0], 'participante.ogg')
                self.assertEqual(kwargs['files']['file'][1].read(), b'whole audio')
                self.assertEqual(kwargs['timeout'], 3600)
                return response

            with patch.object(stt.requests, 'post', side_effect=post) as request:
                segments = list(stt.PiaTranscription().transcribe_file(path))
            self.assertEqual(request.call_count, 1)
        self.assertEqual([(s.start, s.end) for s in segments], [(2.25, 3.5), (93.1, 94.2)])
        self.assertEqual([s.text for s in segments], ['Primeira.', 'Segunda.'])

    def test_compact_conversion_and_cleanup(self):
        commands = []
        def encode(command, **kwargs):
            commands.append(command)
            Path(command[-1]).write_bytes(b'compact mp3')
            return Mock(returncode=0)
        with patch.object(stt.subprocess, 'run', side_effect=encode):
            with patch.object(stt.PiaTranscription, 'transcribe_file', return_value=iter([])) as send:
                list(stt.PiaTranscription().transcribe('original.flac', 105))
                uploaded = send.call_args.args[0]
        command = commands[0]
        self.assertEqual(command[command.index('-ac') + 1], '1')
        self.assertEqual(command[command.index('-ar') + 1], '16000')
        self.assertEqual(command[command.index('-b:a') + 1], '64k')
        self.assertNotIn('-ss', command)
        self.assertNotIn('-t', command)
        self.assertEqual(uploaded.suffix, '.mp3')
        self.assertFalse(uploaded.exists())

    def test_long_flac_skips_conversion(self):
        with patch.object(stt.subprocess, 'run') as convert:
            with patch.object(stt.PiaTranscription, 'transcribe_file', return_value=iter([])) as send:
                list(stt.PiaTranscription().transcribe('original.flac', 16529))
                self.assertEqual(send.call_args.args[0], Path('original.flac'))
            convert.assert_not_called()

    def test_mp3_size_threshold_falls_back_to_original_flac(self):
        for size, expected in ((24999999, '.mp3'), (25000000, '.flac')):
            def encode(command, **kwargs):
                with Path(command[-1]).open('wb') as audio:
                    audio.truncate(size)
                return Mock(returncode=0)
            with self.subTest(size=size), patch.object(stt.subprocess, 'run', side_effect=encode):
                with stt.PiaTranscription().prepare_audio('original.flac') as upload:
                    self.assertEqual(upload.suffix, expected)
                    if expected == '.flac':
                        self.assertEqual(upload, Path('original.flac'))

    def test_conversion_failure_does_not_upload(self):
        with patch.object(stt.subprocess, 'run', return_value=Mock(returncode=1, stderr='erro FFmpeg')):
            with patch.object(stt.requests, 'post') as post:
                with self.assertRaisesRegex(RuntimeError, 'erro FFmpeg'):
                    stt.PiaTranscription().transcribe('original.flac')
                post.assert_not_called()

    def test_silence(self):
        self.assertEqual(stt.PiaTranscription.parse_segments(self.response(text='', segments=[])), [])

    def test_rejects_old_contract_and_invalid_times(self):
        invalid = [self.response(segments=[]), self.response(duration=None),
                   self.response(duration=float('nan')), {'text': 'Sem tempos'}]
        for start, end in ((-1, 2), (2, 1), (1, float('inf')), (1, 106), (True, 2)):
            invalid.append(self.response(segments=[{'start': start, 'end': end, 'text': 'Fala'}]))
        for data in invalid:
            with self.subTest(data=data), self.assertRaisesRegex(RuntimeError, 'timestamps reais'):
                stt.PiaTranscription.parse_segments(data)

    def test_server_error_message_and_upload_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audio.mp3'
            path.write_bytes(b'audio')
            for status in (500, 413, 401):
                response = Mock(status_code=status, json=Mock(return_value={'error': {'message': 'Explicação da PIA'}}))
                with self.subTest(status=status), patch.object(stt.requests, 'post', return_value=response):
                    with self.assertRaisesRegex(RuntimeError, f'HTTP {status}.*Explicação da PIA'):
                        list(stt.PiaTranscription().transcribe_file(path))

    def test_oversized_file_is_rejected_before_request(self):
        with patch.dict(os.environ, {'PIA_STT_MAX_UPLOAD_MIB': '9999'}):  # Ignored: host limit wins.
            with patch.object(stt.Path, 'stat', return_value=Mock(st_size=330712415)):
                with patch.object(stt.requests, 'post') as post:
                    with self.assertRaisesRegex(RuntimeError, '315.*limite configurado é 200'):
                        stt.PiaTranscription().transcribe_file('participante.flac')
                    post.assert_not_called()

    def test_invalid_json_and_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audio.wav'
            path.write_bytes(b'audio')
            response = Mock(status_code=200, json=Mock(side_effect=ValueError))
            with patch.object(stt.requests, 'post', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'JSON válido'):
                    list(stt.PiaTranscription().transcribe_file(path))
            with patch.object(stt.requests, 'post', side_effect=stt.requests.ConnectionError):
                with self.assertRaisesRegex(RuntimeError, 'comunicar com a PIA'):
                    list(stt.PiaTranscription().transcribe_file(path))


if __name__ == '__main__':
    unittest.main()

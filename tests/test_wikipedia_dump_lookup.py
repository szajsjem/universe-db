import bz2
import json
from pathlib import Path
import tempfile
import unittest

from scripts.wikipedia_dump_lookup import WikipediaDump


class WikipediaDumpLookupTest(unittest.TestCase):
    def test_indexed_stream_preserves_page_and_revision_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            names = ['enwiki-20260901-pages-articles-multistream.xml.bz2',
                     'enwiki-20260901-pages-articles-multistream-index.txt.bz2']
            first = bz2.compress(b'<page><title>Other</title><id>1</id><revision><id>10</id><text>Other article</text></revision></page>')
            second = bz2.compress(b'<page><title>Water: chemistry</title><id>2</id><revision><id>20</id><text>Water has formula H2O. &amp; more text.</text></revision></page>')
            (directory / names[0]).write_bytes(first + second)
            (directory / names[1]).write_bytes(bz2.compress(f'0:1:Other\n{len(first)}:2:Water: chemistry\n'.encode()))
            metadata = {'date': '20260901', 'status': 'completed', 'upstream_checksums_complete': True,
                        'files': [{'name': name, 'bytes': (directory / name).stat().st_size, 'sha256': str(i) * 64}
                                  for i, name in enumerate(names)]}
            (directory / 'download-status.json').write_text(json.dumps(metadata))
            lookup = WikipediaDump(directory, {2, 3}, directory / 'lookup.json')
            page = lookup.read(2, 'formula')
            self.assertEqual('20', page['revision_id'])
            self.assertEqual('Water: chemistry', page['title'])
            self.assertIn('H2O', page['excerpt'])
            self.assertIn('& more text', page['excerpt'])
            self.assertFalse(lookup.read(3, 'missing')['found'])
            self.assertEqual(lookup.pages, WikipediaDump(directory, {2, 3}, directory / 'lookup.json').pages)
            with self.assertRaisesRegex(ValueError, 'offset is outside'):
                lookup.read(2, 'formula', offset=999)

    def test_incomplete_dump_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'download-status.json').write_text(json.dumps({'status': 'downloading'}))
            with self.assertRaisesRegex(ValueError, 'checksum verification'):
                WikipediaDump(directory, {2}, directory / 'lookup.json')


if __name__ == '__main__':
    unittest.main()

import glob
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from convert import convert_file, read_metadata, write_metadata


SOURCES_DIR = os.path.join(REPO_ROOT, 'sources')


class ConvertTest(unittest.TestCase):
    """Tests loading a single source into a dict and converting it to a file."""

    def test_read_metadata_loads_each_source_into_dict(self):
        source_files = sorted(glob.glob(os.path.join(SOURCES_DIR, '*.json')))
        self.assertTrue(source_files, 'expected at least one sources/*.json file')

        for source_file in source_files:
            with self.subTest(source=os.path.basename(source_file)):
                metadata = read_metadata(source_file)
                self.assertIsInstance(metadata, dict)
                self.assertTrue(metadata)

    def test_convert_maps_a_single_source_file_to_yaml(self):
        sample = {'Make': 'Acme', 'Model': 'Widget-1000'}

        with tempfile.TemporaryDirectory() as work_dir:
            input_file = os.path.join(work_dir, 'source.json')
            write_metadata(sample, input_file)

            output_file = os.path.join(work_dir, 'converted.yaml')
            converted = convert_file(input_file, output_file)

            self.assertEqual(converted, {
                'Instrument': {'Manufacturer': 'Acme', 'Model': 'Widget-1000'},
            })
            self.assertTrue(os.path.isfile(output_file))
            self.assertEqual(read_metadata(output_file), converted)


if __name__ == '__main__':
    unittest.main()

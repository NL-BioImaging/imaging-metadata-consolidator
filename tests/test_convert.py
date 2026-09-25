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
OUTPUT_DIR = os.path.join(REPO_ROOT, 'output')
SCHEMA_FILE = os.path.join(REPO_ROOT, 'mappings', 'schema.extended.json')
MAPPINGS_FILE = os.path.join(REPO_ROOT, 'mappings', 'mappings.json')


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
                'SourceMap': {'Instrument.Manufacturer': 'Make', 'Instrument.Model': 'Model'},
            })
            self.assertTrue(os.path.isfile(output_file))
            self.assertEqual(read_metadata(output_file), converted)


class OutputFolderTest(unittest.TestCase):
    """output/ must hold what converting sources/ with the current mappings gives today."""

    REGENERATE = 'rerun: python src/main.py convert --input sources --output output'

    def test_output_holds_one_file_per_source(self):
        sources = {os.path.splitext(os.path.basename(path))[0] for path in glob.glob(os.path.join(SOURCES_DIR, '*.json'))}
        converted = {os.path.splitext(os.path.basename(path))[0] for path in glob.glob(os.path.join(OUTPUT_DIR, '*.yaml'))}
        self.assertEqual(converted, sources, self.REGENERATE)

    def test_output_is_up_to_date(self):
        with tempfile.TemporaryDirectory() as directory:
            for source_file in sorted(glob.glob(os.path.join(SOURCES_DIR, '*.json'))):
                name = os.path.splitext(os.path.basename(source_file))[0] + '.yaml'
                with self.subTest(source=name):
                    fresh = os.path.join(directory, name)
                    convert_file(source_file, fresh, SCHEMA_FILE, MAPPINGS_FILE)
                    self.assertEqual(read_metadata(os.path.join(OUTPUT_DIR, name)), read_metadata(fresh),
                                     self.REGENERATE)


if __name__ == '__main__':
    unittest.main()

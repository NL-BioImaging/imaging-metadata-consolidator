import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from AcquisitionMetadataMapper import AcquisitionMetadataMapper


class AcquisitionMetadataMapperTest(unittest.TestCase):
    """Tests the dict-in/dict-out schema mapping (no file I/O)."""

    @classmethod
    def setUpClass(cls):
        cls.mapper = AcquisitionMetadataMapper()

    def test_convert_metadata_accepts_in_memory_dict(self):
        sample = {'Make': 'Acme', 'Model': 'Widget-1000'}

        converted = self.mapper.convert_metadata(sample)

        self.assertEqual(converted, {
            'Instrument': {'Manufacturer': 'Acme', 'Model': 'Widget-1000'},
            'SourceMap': {'Instrument.Manufacturer': 'Make', 'Instrument.Model': 'Model'},
        })

    def test_convert_metadata_rejects_non_dict(self):
        with self.assertRaises(TypeError):
            self.mapper.convert_metadata(['not', 'a', 'dict'])

    def test_huygens_sampling_sizes_map_to_pixels(self):
        # Checked against DNAcropSmall.ome.json, which carries both this annotation and the image's own OME Pixels
        annotation = {'Geometry': {'SamplingSizes': {'DeltaX': 0.064967, 'DeltaY': 0.064967, 'DeltaZ': 0.2128,
                                                     'DeltaT': 1.0}},
                      'ChannelData': [{'RefrIndexLensMedium': 1.518}]}

        converted = self.mapper.convert_metadata({'Annotation:CustomAttributes:SVI:Image:0': annotation})

        self.assertEqual(converted['Image']['Pixels'], {'PhysicalSizeX': 0.064967, 'PhysicalSizeY': 0.064967,
                                                        'PhysicalSizeZ': 0.2128, 'TimeIncrement': 1.0})
        self.assertEqual(converted['Settings']['ObjectiveSettings']['ImmersionLiquid'], {'RefractiveIndex': 1.518})


class LosslessMappingTest(unittest.TestCase):
    """Collisions, empty values and collapsed keys must never drop metadata."""

    def mapper_for(self, mappings):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        schema_file = os.path.join(directory, 'schema.json')
        mappings_file = os.path.join(directory, 'mappings.json')
        with open(schema_file, 'w', encoding='utf-8') as file:
            json.dump({}, file)
        with open(mappings_file, 'w', encoding='utf-8') as file:
            json.dump(mappings, file)
        return AcquisitionMetadataMapper(schema_file, mappings_file)

    def test_colliding_value_falls_back_to_its_source_path(self):
        mapper = self.mapper_for({'a': 'T', 'b': 'T'})

        converted = mapper.convert_metadata({'a': 1, 'b': 2})

        self.assertEqual(converted, {'T': 1, 'b': 2, 'SourceMap': {'T': 'a', 'b': 'b'}})

    def test_value_below_a_scalar_falls_back_to_its_source_path(self):
        mapper = self.mapper_for({'a': 'T', 'b': 'T.X'})

        converted = mapper.convert_metadata({'a': 1, 'b': 2})

        self.assertEqual(converted, {'T': 1, 'b': 2, 'SourceMap': {'T': 'a', 'b': 'b'}})

    def test_refuses_to_overwrite_when_fallback_is_taken_too(self):
        mapper = self.mapper_for({'a': 'b'})

        with self.assertRaises(ValueError):
            mapper.convert_metadata({'a': 1, 'b': 2})

    def test_empty_containers_are_kept(self):
        converted = self.mapper_for({}).convert_metadata({'a': {}, 'b': [], 'c': None})

        self.assertEqual(converted, {'a': {}, 'b': [], 'c': None,
                                     'SourceMap': {'a': 'a', 'b': 'b', 'c': 'c'}})

    def test_numeric_collapsed_key_is_kept(self):
        mapper = self.mapper_for({'Detectors.*': 'D[]'})

        converted = mapper.convert_metadata({'Detectors': {'3': {'gain': 1}}})

        self.assertEqual(converted['D'], [{'gain': 1, 'id': '3'}])
        self.assertEqual(converted['SourceMap']['D[0].id'], 'Detectors.3')

    def test_collapsed_key_is_kept_beside_an_existing_id(self):
        mapper = self.mapper_for({'Detectors.*': 'D[]'})

        converted = mapper.convert_metadata({'Detectors': {'QBSD': {'id': 7, 'ID': 8}}})

        self.assertEqual(converted['D'], [{'id': 7, 'ID': 8, 'SourceKey': 'QBSD'}])

    def test_whole_path_wildcard_key_is_kept(self):
        mapper = self.mapper_for({'Image:*': 'Images[]'})

        converted = mapper.convert_metadata({'Image:0': {'x': 1}})

        self.assertEqual(converted['Images'], [{'x': 1, 'SourceKey': 'Image:0'}])
        self.assertEqual(converted['SourceMap'], {'Images[0].x': 'Image:0.x', 'Images[0].SourceKey': 'Image:0'})

    def test_rule_inside_a_list_item_writes_from_the_root(self):
        mapper = self.mapper_for({'Image:*': 'Images[]', 'Image:*.History.Version': 'Software.Version'})

        converted = mapper.convert_metadata({'Image:0': {'History': {'Version': '1.0', 'Count': 5}}})

        self.assertEqual(converted['Software'], {'Version': '1.0'})
        self.assertEqual(converted['Images'], [{'History': {'Count': 5}, 'SourceKey': 'Image:0'}])
        self.assertEqual(converted['SourceMap']['Software.Version'], 'Image:0.History.Version')

    def test_rule_in_each_list_item_falls_back_into_the_item_on_collision(self):
        mapper = self.mapper_for({'Channels.Refr': 'Medium.RefractiveIndex'})

        converted = mapper.convert_metadata({'Channels': [{'Refr': 1.4}, {'Refr': 1.5}]})

        self.assertEqual(converted['Medium'], {'RefractiveIndex': 1.4})
        self.assertEqual(converted['Channels'], [{}, {'Refr': 1.5}])
        self.assertEqual(converted['SourceMap'], {'Medium.RefractiveIndex': 'Channels[0].Refr',
                                                  'Channels[1].Refr': 'Channels[1].Refr'})

    def test_list_target_taken_by_a_value_falls_back_to_the_source_path(self):
        mapper = self.mapper_for({'Name': 'D', 'Detectors.*': 'D[]'})

        converted = mapper.convert_metadata({'Name': 'x', 'Detectors': {'QBSD': {'gain': 1}}})

        self.assertEqual(converted['D'], 'x')
        self.assertEqual(converted['Detectors'], {'QBSD': {'gain': 1, 'id': 'QBSD'}})
        self.assertEqual(converted['SourceMap']['Detectors.QBSD.gain'], 'Detectors.QBSD.gain')


if __name__ == '__main__':
    unittest.main()

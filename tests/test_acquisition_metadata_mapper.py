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

    def test_aperio_svs_fields_map_to_image_and_instrument(self):
        # OriginalWidth/Height match the description's "28448x21839" header; Left/Top are mm on the slide,
        # the scan area's position, not crop edges
        svs = {'AppMag': 20, 'MPP': 0.4936, 'OriginalWidth': 28448, 'OriginalHeight': 21839,
               'ScanScope ID': 'SS1735', 'ImageID': 18489, 'Left': 29.282969, 'Top': 13.628824}

        converted = self.mapper.convert_metadata(svs)

        self.assertEqual(converted['Image'], {'Pixels': {'PhysicalSizeX': 0.4936, 'PhysicalSizeY': 0.4936,
                                                         'SizeX': 28448, 'SizeY': 21839},
                                              'ID': 18489,
                                              'Plane': {'PositionX': 29.282969, 'PositionY': 13.628824}})
        self.assertEqual(converted['Magnification'], {'Objective': {'Magnification': 20}})
        self.assertEqual(converted['Instrument'], {'ID': 'SS1735'})

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

    def mapper_for(self, mappings, combinations=()):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        files = {}
        for name, content in (('schema', {}), ('mappings', mappings), ('combinations', list(combinations))):
            files[name] = os.path.join(directory, f'{name}.json')
            with open(files[name], 'w', encoding='utf-8') as file:
                json.dump(content, file)
        return AcquisitionMetadataMapper(files['schema'], files['mappings'], files['combinations'])

    def test_rule_naming_several_targets_copies_the_value_to_each(self):
        mapper = self.mapper_for({'MPP': ['Pixels.PhysicalSizeX', 'Pixels.PhysicalSizeY']})

        converted = mapper.convert_metadata({'MPP': 0.5})

        self.assertEqual(converted, {'Pixels': {'PhysicalSizeX': 0.5, 'PhysicalSizeY': 0.5},
                                     'SourceMap': {'Pixels.PhysicalSizeX': 'MPP', 'Pixels.PhysicalSizeY': 'MPP'}})

    def test_copy_to_a_further_target_never_overwrites(self):
        mapper = self.mapper_for({'MPP': ['X', 'Y'], 'Height': 'Y'})

        converted = mapper.convert_metadata({'Height': 7, 'MPP': 0.5})

        self.assertEqual(converted, {'Y': 7, 'X': 0.5, 'SourceMap': {'Y': 'Height', 'X': 'MPP'}})

    def test_several_targets_for_a_group_are_refused(self):
        mapper = self.mapper_for({'Beam': ['A', 'B']})

        with self.assertRaises(ValueError):
            mapper.convert_metadata({'Beam': {'WD': 1}})

    def test_combination_adds_an_iso_timestamp_and_keeps_its_parts(self):
        mapper = self.mapper_for({}, [{'target': 'Image.AcquisitionDate', 'sources': ['Date', 'Time', 'Time Zone'],
                                       'format': '%m/%d/%y %H:%M:%S GMT%z'}])

        converted = mapper.convert_metadata({'Date': '10/19/15', 'Time': '17:18:12', 'Time Zone': 'GMT-05:00'})

        self.assertEqual(converted['Image'], {'AcquisitionDate': '2015-10-19T17:18:12-05:00'})
        self.assertEqual([converted[key] for key in ('Date', 'Time', 'Time Zone')], ['10/19/15', '17:18:12', 'GMT-05:00'])
        self.assertEqual(converted['SourceMap']['Image.AcquisitionDate'], ['Date', 'Time', 'Time Zone'])

    def test_combination_is_left_out_when_a_part_is_missing_or_does_not_parse(self):
        mapper = self.mapper_for({}, [{'target': 'D', 'sources': ['Date', 'Time'], 'format': '%m/%d/%y %H:%M:%S'}])

        self.assertNotIn('D', mapper.convert_metadata({'Date': '10/19/15'}))
        self.assertNotIn('D', mapper.convert_metadata({'Date': '10/19/15', 'Time': 'noon'}))

    def test_combination_never_overwrites(self):
        mapper = self.mapper_for({'Stamp': 'D'}, [{'target': 'D', 'sources': ['Date', 'Time'],
                                                   'format': '%m/%d/%y %H:%M:%S'}])

        converted = mapper.convert_metadata({'Stamp': 'kept', 'Date': '10/19/15', 'Time': '17:18:12'})

        self.assertEqual(converted['D'], 'kept')

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

    def test_vendor_wrapper_is_left_out_of_rule_paths_only(self):
        mapper = self.mapper_for({'Make': 'Instrument.Manufacturer'})

        converted = mapper.convert_metadata({'FEI_TITAN': {'Make': 'Acme', 'databarHeight': 0}})

        self.assertEqual(converted, {'Instrument': {'Manufacturer': 'Acme'}, 'FEI_TITAN': {'databarHeight': 0},
                                     'SourceMap': {'Instrument.Manufacturer': 'FEI_TITAN.Make',
                                                   'FEI_TITAN.databarHeight': 'FEI_TITAN.databarHeight'}})

    def test_wrapped_value_colliding_with_a_top_level_one_is_kept(self):
        mapper = self.mapper_for({'DateTime': 'Image.AcquisitionDate', 'datetime': 'Image.AcquisitionDate'})

        converted = mapper.convert_metadata({'DateTime': '10:54:29', 'OlympusSIS': {'datetime': '10:54:00'}})

        self.assertEqual(converted['Image'], {'AcquisitionDate': '10:54:29'})
        self.assertEqual(converted['OlympusSIS'], {'datetime': '10:54:00'})

    def test_key_named_by_a_rule_is_not_a_wrapper(self):
        mapper = self.mapper_for({'Make': 'Instrument.Manufacturer', 'Tag.Make': 'Other.Make'})

        converted = mapper.convert_metadata({'Tag': {'Make': 'Acme'}})

        self.assertEqual(converted['Other'], {'Make': 'Acme'})

    def test_key_whose_contents_resolve_no_better_is_not_a_wrapper(self):
        mapper = self.mapper_for({'Make': 'Instrument.Manufacturer'})

        converted = mapper.convert_metadata({'Blob': {'odd': 1}})

        self.assertEqual(converted, {'Blob': {'odd': 1}, 'SourceMap': {'Blob.odd': 'Blob.odd'}})

    def test_list_target_taken_by_a_value_falls_back_to_the_source_path(self):
        mapper = self.mapper_for({'Name': 'D', 'Detectors.*': 'D[]'})

        converted = mapper.convert_metadata({'Name': 'x', 'Detectors': {'QBSD': {'gain': 1}}})

        self.assertEqual(converted['D'], 'x')
        self.assertEqual(converted['Detectors'], {'QBSD': {'gain': 1, 'id': 'QBSD'}})
        self.assertEqual(converted['SourceMap']['Detectors.QBSD.gain'], 'Detectors.QBSD.gain')


if __name__ == '__main__':
    unittest.main()

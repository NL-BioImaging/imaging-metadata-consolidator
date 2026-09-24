import glob
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from AcquisitionMetadataMapper import AcquisitionMetadataMapper
from DatasetExporter import PROVENANCE_ENTITIES, DatasetExporter, export_file, fits
from convert import read_metadata


PROFILE_FILE = os.path.join(REPO_ROOT, 'models', 'fullSchema.yaml')
SOURCES_DIR = os.path.join(REPO_ROOT, 'sources')
EXTENDED_PROFILE_FILE = os.path.join(REPO_ROOT, 'models', 'schema.extended.yaml')
EXPORT_DIR = os.path.join(REPO_ROOT, 'export')
CHECKSUM = '0' * 64


def unknown_keys(exporter, node, entity, path=''):
    """Paths of keys in `node` that `entity` does not declare, recursing into nested entities."""
    fields = exporter.entities[entity]
    unknown = []
    for key, value in node.items():
        key_path = f'{path}.{key}' if path else key
        field = fields.get(key)
        child = exporter._nested_entity(field) if field is not None else None
        if field is None:
            unknown.append(key_path)
        elif child is not None:
            records = value if isinstance(value, list) else [value]
            for index, record in enumerate(records):
                record_path = f'{key_path}[{index}]' if isinstance(value, list) else key_path
                unknown += unknown_keys(exporter, record, child, record_path)
    return unknown


class FitsTest(unittest.TestCase):
    def test_types_must_match_exactly(self):
        self.assertTrue(fits('a', {'type': 'string'}))
        self.assertFalse(fits(1, {'type': 'string'}))
        self.assertTrue(fits(1, {'type': 'integer'}))
        self.assertFalse(fits(True, {'type': 'integer'}))
        self.assertFalse(fits(1.5, {'type': 'integer'}))
        self.assertTrue(fits(1, {'type': 'float'}))
        self.assertFalse(fits(None, {'type': 'string'}))
        self.assertTrue(fits(['a', 'b'], {'type': 'list', 'items': 'string'}))
        self.assertFalse(fits(['a', 1], {'type': 'list', 'items': 'string'}))

    def test_constraints_must_hold(self):
        self.assertTrue(fits('µm', {'type': 'string', 'constraints': {'enum': ['µm']}}))
        self.assertFalse(fits('um', {'type': 'string', 'constraints': {'enum': ['µm']}}))
        self.assertFalse(fits('ABC', {'type': 'string', 'constraints': {'pattern': '^[a-z]+$'}}))


class DatasetExporterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exporter = DatasetExporter(PROFILE_FILE)

    def export(self, converted):
        return self.exporter.export(converted, 'source.json', CHECKSUM)

    def test_fitting_value_goes_into_its_field_with_a_mapping(self):
        dataset = self.export({'Image': {'Name': 'x'}, 'SourceMap': {'Image.Name': 'title'}})

        image = dataset['Image'][0]
        self.assertEqual(image['Name'], 'x')
        self.assertEqual(image['SourceFile'][0]['Mapping'],
                         [{'ID': 'SourceMapping:0', 'Field': 'Image[0].Name', 'Source': 'title'}])
        self.assertNotIn('CustomProperties', image)

    def test_value_that_does_not_fit_becomes_a_property(self):
        dataset = self.export({'Image': {'Pixels': {'PhysicalSizeXUnit': 'um', 'SizeX': 1.5}},
                               'SourceMap': {'Image.Pixels.PhysicalSizeXUnit': 'unit',
                                             'Image.Pixels.SizeX': 'Image.Pixels.SizeX'}})

        image = dataset['Image'][0]
        self.assertEqual(image['Pixels'], {})
        self.assertEqual(image['CustomProperties'], [
            {'ID': 'Property:0', 'Name': 'unit', 'Value': '"um"', 'SchemaPath': 'Image.Pixels.PhysicalSizeXUnit',
             'Source': 'SourceFile:0'},
            {'ID': 'Property:1', 'Name': 'Image.Pixels.SizeX', 'Value': '1.5', 'Source': 'SourceFile:0'},
        ])

    def test_entity_is_placed_along_the_profile_tree(self):
        dataset = self.export({'Image': {'Plane': {'TheZ': 3}}, 'Magnification': {'Objective': {'LensNA': 1.4}},
                               'SourceMap': {'Image.Plane.TheZ': 'z', 'Magnification.Objective.LensNA': 'na'}})

        self.assertEqual(dataset['Image'][0]['Pixels']['Plane'], [{'TheZ': 3}])
        self.assertEqual(dataset['Instrument'][0]['Objective'], [{'LensNA': 1.4}])

    def test_category_and_title_name_one_entity(self):
        dataset = self.export({'Fluorescence_LightSource': {'Filament': {'Name': 'lamp'}},
                               'SourceMap': {'Fluorescence_LightSource.Filament.Name': 'lamp'}})

        self.assertEqual(dataset['Instrument'][0]['Fluorescence_LightSource_Filament'], [{'Name': 'lamp'}])

    def test_unmodelled_values_go_to_the_nearest_anchor(self):
        dataset = self.export({'Instrument': {'Manufacturer': 'Acme'}, 'Scan': {'FrameTime': {'Value': 2}},
                               'SourceMap': {'Instrument.Manufacturer': 'Make',
                                             'Scan.FrameTime.Value': 'Scan.FrameTime'}})

        self.assertEqual([p['Name'] for p in dataset['Instrument'][0]['CustomProperties']], ['Make'])
        self.assertEqual([p['Name'] for p in dataset['CustomProperties']], ['Scan.FrameTime'])

    def test_taken_field_keeps_the_second_value_as_a_property(self):
        dataset = self.export({'Image': {'Name': 'a'}, 'Other': {'Image': {'Name': 'b'}},
                               'SourceMap': {'Image.Name': 'n1', 'Other.Image.Name': 'n2'}})

        image = dataset['Image'][0]
        self.assertEqual(image['Name'], 'a')
        self.assertEqual([(p['Name'], p['Value']) for p in image['CustomProperties']], [('n2', '"b"')])

    def test_null_and_empty_values_become_properties(self):
        dataset = self.export({'a': None, 'b': {}, 'SourceMap': {'a': 'a', 'b': 'b'}})

        self.assertEqual([p['Value'] for p in dataset['CustomProperties']], ['null', '{}'])

    def test_sources_export_only_declared_fields(self):
        mapper = AcquisitionMetadataMapper()
        for source_file in sorted(glob.glob(os.path.join(SOURCES_DIR, '*.json'))):
            with self.subTest(source=os.path.basename(source_file)):
                dataset = self.export(mapper.convert_metadata(read_metadata(source_file)))
                self.assertEqual(unknown_keys(self.exporter, dataset, 'OME'), [])

    def test_sources_export_only_declared_fields_of_the_extended_profile(self):
        exporter = DatasetExporter(os.path.join(REPO_ROOT, 'models', 'schema.extended.yaml'))
        mapper = AcquisitionMetadataMapper()
        for source_file in sorted(glob.glob(os.path.join(SOURCES_DIR, '*.json'))):
            with self.subTest(source=os.path.basename(source_file)):
                converted = mapper.convert_metadata(read_metadata(source_file))
                dataset = exporter.export(converted, 'source.json', CHECKSUM)
                self.assertEqual(unknown_keys(exporter, dataset, 'OME'), [])

    def test_provenance_entities_are_not_placement_targets(self):
        for entity in PROVENANCE_ENTITIES:
            self.assertNotIn(entity, self.exporter.paths)


class ExportFolderTest(unittest.TestCase):
    """export/ must hold what exporting sources/ against the extended profile gives today."""

    REGENERATE = ('rerun: python src/main.py export --input sources --output export '
                  '--profile models/schema.extended.yaml')

    def test_export_holds_one_dataset_per_source(self):
        sources = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(SOURCES_DIR, '*.json'))}
        exported = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(EXPORT_DIR, '*.yaml'))}
        self.assertEqual(exported, sources, self.REGENERATE)

    def test_export_is_up_to_date(self):
        mapper = AcquisitionMetadataMapper()
        exporter = DatasetExporter(EXTENDED_PROFILE_FILE)
        with tempfile.TemporaryDirectory() as directory:
            for source_file in sorted(glob.glob(os.path.join(SOURCES_DIR, '*.json'))):
                name = os.path.splitext(os.path.basename(source_file))[0] + '.yaml'
                with self.subTest(source=name):
                    fresh = os.path.join(directory, name)
                    export_file(source_file, fresh, mapper, exporter)
                    self.assertEqual(read_metadata(os.path.join(EXPORT_DIR, name)), read_metadata(fresh),
                                     self.REGENERATE)


if __name__ == '__main__':
    unittest.main()

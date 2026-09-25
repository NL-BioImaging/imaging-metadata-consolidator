import json
import os
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from ProfileConverter import ROOT_ENTITY, ProfileConverter, ProfileExtender, XsdContainment, write_profile


JSON_SCHEMA_FILE = os.path.join(REPO_ROOT, 'models', 'fullSchema.json')
XSD_FILE = os.path.join(REPO_ROOT, 'models', 'LiMi_XMLSchema.xsd')
PROFILE_FILE = os.path.join(REPO_ROOT, 'models', 'fullSchema.yaml')
EXTENDED_PROFILE_FILE = os.path.join(REPO_ROOT, 'models', 'schema.extended.yaml')
SCHEMA_TREE_FILE = os.path.join(REPO_ROOT, 'mappings', 'schema.json')
EXTENDED_SCHEMA_TREE_FILE = os.path.join(REPO_ROOT, 'mappings', 'schema.extended.json')

# Shared definitions the JSON never nests: each parent has its own inline copy instead (e.g.
# Arc_IlluminationWavelengthRange), and Laser.Pump links to Laser rather than to Pump.
UNREACHABLE = {
    'IlluminationWavelengthRange', 'LEDModule', 'Pump', 'ReflectanceRange', 'ReflectionWavelengthRangeSettings',
    'TransmissionWavelengthRangeSettings', 'TransmittanceRange', 'WavelengthProfileFile', 'WavelengthRange',
}

SYNTHETIC_XSD = """<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Root">
    <xs:complexType><xs:sequence>
      <xs:element ref="DeviceGroup" maxOccurs="unbounded"/>
      <xs:element name="Settings" type="SettingsType"/>
    </xs:sequence></xs:complexType>
  </xs:element>
  <xs:element name="DeviceGroup" abstract="true"/>
  <xs:element name="CameraGroup" abstract="true" substitutionGroup="DeviceGroup"/>
  <xs:element name="Laser" substitutionGroup="DeviceGroup"/>
  <xs:element name="CCD" substitutionGroup="CameraGroup"/>
  <xs:complexType name="BaseSettings"><xs:sequence>
    <xs:element name="Gain"/>
  </xs:sequence></xs:complexType>
  <xs:complexType name="SettingsType"><xs:complexContent><xs:extension base="BaseSettings"><xs:sequence>
    <xs:element name="Offset"/>
  </xs:sequence></xs:extension></xs:complexContent></xs:complexType>
  <xs:element name="Detector" type="SettingsType"/>
</xs:schema>
"""


def nested_children(entities, name):
    return [f['items'] for f in entities[name]['fields']
            if f['type'] in ('entity', 'list') and f['items'] in entities]


class XsdContainmentTest(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile('w', suffix='.xsd', delete=False, encoding='utf-8') as file:
            file.write(SYNTHETIC_XSD)
        self.addCleanup(os.remove, file.name)
        self.containment = XsdContainment(file.name)

    def test_substitution_groups_expand_to_concrete_members(self):
        self.assertEqual(self.containment.children('Root'),
                         [('CCD', 'unbounded'), ('Laser', 'unbounded'), ('Settings', '1')])

    def test_named_type_includes_extension_base(self):
        self.assertEqual(self.containment.children('Detector'), [('Gain', '1'), ('Offset', '1')])


class ProfileConverterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        converter = ProfileConverter(JSON_SCHEMA_FILE, XSD_FILE)
        cls.profile = converter.convert()
        cls.entity_name = converter._entity_name
        with open(JSON_SCHEMA_FILE, encoding='utf-8') as file:
            cls.schemas = json.load(file)

    def test_committed_profile_is_up_to_date(self):
        with open(PROFILE_FILE, encoding='utf-8') as file:
            committed = yaml.safe_load(file)
        self.assertEqual(committed, self.profile, 'rerun: python src/main.py profile')

    def test_every_json_property_becomes_a_field(self):
        entities = self.profile['entities']
        for schema in self.schemas:
            field_names = {f['name'] for f in entities[self.entity_name(schema)]['fields']}
            self.assertLessEqual(set(schema['properties']), field_names, schema['title'])

    def test_single_entity_fields_name_an_existing_entity(self):
        entities = self.profile['entities']
        for name, entity in entities.items():
            for field in entity['fields']:
                if field['type'] == 'entity':
                    self.assertIn(field['items'], entities, name)

    def test_entities_are_reachable_from_root(self):
        entities = self.profile['entities']
        self.assertEqual(self.profile['root_entity'], ROOT_ENTITY)
        reachable = set()
        pending = [ROOT_ENTITY]
        while pending:
            name = pending.pop()
            if name not in reachable:
                reachable.add(name)
                pending += nested_children(entities, name)
        self.assertEqual(set(entities) - reachable, UNREACHABLE)

    def test_xsd_containment_is_added(self):
        entities = self.profile['entities']
        self.assertEqual(nested_children(entities, ROOT_ENTITY), ['Experiment', 'Instrument', 'Image', 'Property'])
        self.assertIn('Pixels', nested_children(entities, 'Image'))
        self.assertLessEqual({'Channel', 'Plane'}, set(nested_children(entities, 'Pixels')))
        self.assertLessEqual({'Fluorescence_LightSource_Filament', 'Transmitted_LightSource_Filament', 'Objective'},
                             set(nested_children(entities, 'Instrument')))

    def test_existing_json_field_takes_precedence_over_xsd_child(self):
        fields = [f for f in self.profile['entities']['BeamSplitter']['fields']
                  if f['name'] == 'TransmittanceProfileFile']
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]['type'], 'string')

    def test_unmodelled_metadata_has_a_home_at_each_anchor(self):
        entities = self.profile['entities']
        for anchor in ('OME', 'Image', 'Instrument'):
            self.assertIn('Property', nested_children(entities, anchor), anchor)
        self.assertIn('SourceFile', nested_children(entities, 'Image'))
        self.assertEqual([f['name'] for f in entities['Property']['fields']],
                         ['ID', 'Name', 'Value', 'SchemaPath', 'Unit', 'Source'])
        self.assertIn('SourceMapping', nested_children(entities, 'SourceFile'))

    def test_source_file_checksum_must_be_sha256_hex(self):
        checksum = next(f for f in self.profile['entities']['SourceFile']['fields'] if f['name'] == 'Checksum')
        self.assertTrue(checksum['required'])
        self.assertEqual(checksum['constraints'], {'pattern': '^[0-9a-f]{64}$'})

    def test_tier_is_never_required(self):
        for name, entity in self.profile['entities'].items():
            for field in entity['fields']:
                if field['name'] == 'Tier':
                    self.assertFalse(field['required'], name)

    def test_description_names_the_limi_model_version(self):
        self.assertIn('LiMi model version 2.01.1', self.profile['description'])

    def test_version_is_written_as_a_string(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, 'profile.yaml')
            write_profile(self.profile, filename)
            with open(filename, encoding='utf-8') as file:
                self.assertEqual(yaml.safe_load(file)['version'], '2.1')


def read_json(filename):
    with open(filename, encoding='utf-8') as file:
        return json.load(file)


def read_yaml(filename):
    with open(filename, encoding='utf-8') as file:
        return yaml.safe_load(file)


def fields_of(entity):
    return {f['name']: f for f in entity['fields']}


class ProfileExtenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = read_yaml(PROFILE_FILE)
        cls.extender = ProfileExtender(cls.base, read_json(EXTENDED_SCHEMA_TREE_FILE), read_json(SCHEMA_TREE_FILE))
        cls.profile = cls.extender.extend('LiMi-extended', 'test')
        cls.entities = cls.profile['entities']

    def test_committed_extended_profile_is_up_to_date(self):
        committed = read_yaml(EXTENDED_PROFILE_FILE)
        self.assertEqual(committed['entities'], self.entities, 'rerun: python src/main.py profile')

    def test_base_profile_is_not_modified(self):
        self.assertEqual(read_yaml(PROFILE_FILE), self.base)

    def test_no_base_field_is_replaced(self):
        for name, entity in self.base['entities'].items():
            extended = fields_of(self.entities[name])
            for field_name, field in fields_of(entity).items():
                self.assertEqual(extended[field_name], field, f'{name}.{field_name}')

    def test_additions_go_on_the_profile_entity(self):
        self.assertLessEqual({'Manufacturer', 'Model', 'Vacuum'}, set(fields_of(self.entities['Instrument'])))
        self.assertLessEqual({'CropHint', 'Corrections'}, set(fields_of(self.entities['Image'])))
        self.assertLessEqual({'Medium', 'RefractiveIndex'}, set(fields_of(self.entities['ObjectiveSettings'])))

    def test_groups_without_an_entity_go_under_the_root(self):
        root = fields_of(self.entities[ROOT_ENTITY])
        for group in ('ElectronBeam', 'Scan', 'Detector', 'Software', 'SamplePositioning'):
            self.assertEqual(root[group]['items'], group)
        stage = fields_of(self.entities['SamplePositioning'])['Stage']
        self.assertEqual(stage['items'], 'SamplePositioning_Stage')
        self.assertEqual(fields_of(self.entities['ElectronBeam'])['WorkingDistance']['items'],
                         'ElectronBeam_WorkingDistance')

    def test_added_entities_are_identified_by_an_optional_id(self):
        for name in self.extender.added_entities:
            identifiers = [f for f in self.entities[name]['fields'] if f.get('is_identifier')]
            self.assertEqual([(f['name'], f['required']) for f in identifiers], [('ID', False)], name)

    def test_existing_fields_are_skipped_not_replaced(self):
        self.assertEqual(len(self.extender.skipped), 2)
        self.assertEqual(fields_of(self.entities[ROOT_ENTITY])['CustomProperties']['items'], 'Property')

    def test_added_entities_are_reachable_from_root(self):
        reachable = set()
        pending = [ROOT_ENTITY]
        while pending:
            name = pending.pop()
            if name not in reachable:
                reachable.add(name)
                pending += nested_children(self.entities, name)
        self.assertEqual(set(self.entities) - reachable, UNREACHABLE)


if __name__ == '__main__':
    unittest.main()

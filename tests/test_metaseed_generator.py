import os
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from MetaseedGenerator import MetaseedGenerator


MODEL_FILE = os.path.join(REPO_ROOT, 'models', 'imaging.yaml')
PROFILE_FILE = os.path.join(REPO_ROOT, 'models', 'imaging.metaseed.yaml')

# The LiMi XSD references a LightSensor (LightSensorRef) but no element contains one.
UNREACHABLE = {'LightSensor'}


SYNTHETIC_MODEL = """
id: https://example.org/synthetic
name: synthetic
version: 1.2.3
prefixes: {linkml: https://w3id.org/linkml/}
imports: [linkml:types]
default_range: string
types:
  LSID: {typeof: string, pattern: '\\S+:\\S+'}
  LightSourceID: {typeof: LSID}
enums:
  Medium: {permissible_values: {Cu: {}, Ar: {}}}
  Role: {permissible_values: {Transmitted: {}, Fluorescence: {}}}
slots:
  ObjectType: {range: string, designates_type: true}
classes:
  Instrument:
    tree_root: true
    attributes:
      ID: {identifier: true, range: LSID}
      LightSource: {range: LightSource, multivalued: true, inlined_as_list: true, required: true}
      Range: {range: WavelengthRange, multivalued: true, inlined_as_list: true}
      Sensor: {range: Sensor, inlined: false}
      Label: {range: Label, inlined: true}
  Sensor:
    attributes:
      ID: {identifier: true}
  Label:
    attributes:
      Text: {range: string}
  LightSource:
    abstract: true
    slots: [ObjectType]
    attributes:
      ID: {identifier: true, range: LightSourceID}
      Power: {range: float, minimum_value: 0}
      PowerUnit: {range: string, ifabsent: string(mW)}
      Role: {range: Role, multivalued: true}
  Laser:
    is_a: LightSource
    attributes:
      Medium: {range: Medium}
      Pump: {range: Laser, inlined: false}
  Filament:
    is_a: LightSource
  WavelengthRange:
    attributes:
      CutIn: {range: float}
  IlluminationWavelengthRange:
    is_a: WavelengthRange
"""


class MetaseedGeneratorTest(unittest.TestCase):
    """The LinkML-to-metaseed rules, on a minimal synthetic model."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            model = os.path.join(folder, 'synthetic.yaml')
            with open(model, 'w', encoding='utf-8') as file:
                file.write(SYNTHETIC_MODEL)
            cls.profile = MetaseedGenerator(model).generate()
        cls.entities = cls.profile['entities']
        cls.fields = {name: {field['name']: field for field in entity['fields']} for name, entity in cls.entities.items()}

    def test_header(self):
        self.assertEqual((self.profile['name'], self.profile['version'], self.profile['root_entity']),
                         ('synthetic', '1.2', 'Instrument'))

    def test_abstract_class_is_one_field_per_subtype(self):
        instrument = self.fields['Instrument']
        self.assertEqual((instrument['Laser']['items'], instrument['Filament']['items']), ('Laser', 'Filament'))
        self.assertNotIn('LightSource', instrument)
        self.assertNotIn('LightSource', self.entities)
        self.assertFalse(instrument['Laser']['required'])

    def test_inherited_slots_written_out(self):
        self.assertEqual(set(self.fields['Laser']), {'ID', 'Power', 'PowerUnit', 'Role', 'Medium', 'Pump'})
        self.assertEqual(set(self.fields['Filament']), {'ID', 'Power', 'PowerUnit', 'Role'})

    def test_concrete_range_is_not_expanded(self):
        self.assertEqual(self.fields['Instrument']['Range']['items'], 'WavelengthRange')
        self.assertNotIn('IlluminationWavelengthRange', self.entities)

    def test_reference_is_an_id_string(self):
        pump = self.fields['Laser']['Pump']
        self.assertEqual((pump['type'], pump['reference']), ('string', 'Laser.ID'))

    def test_constraints_from_types_enums_and_slots(self):
        self.assertEqual(self.fields['Laser']['ID']['constraints'], {'pattern': '\\S+:\\S+'})
        self.assertTrue(self.fields['Laser']['ID']['is_identifier'])
        self.assertEqual(self.fields['Laser']['Medium']['constraints'], {'enum': ['Cu', 'Ar']})
        self.assertEqual(self.fields['Laser']['Power']['constraints'], {'minimum': 0})
        role = self.fields['Laser']['Role']
        self.assertEqual((role['type'], role['items'], role['constraints']),
                         ('list', 'string', {'enum': ['Transmitted', 'Fluorescence']}))
        self.assertEqual(self.fields['Laser']['PowerUnit']['example'], 'mW')
        self.assertNotIn('ObjectType', self.fields['Laser'])


    def test_reference_to_a_class_no_entity_holds_is_a_plain_string(self):
        sensor = self.fields['Instrument']['Sensor']
        self.assertEqual(sensor['type'], 'string')
        self.assertNotIn('reference', sensor)
        self.assertNotIn('Sensor', self.entities)

    def test_identifier_added_where_metaseed_would_take_free_text(self):
        self.assertEqual(list(self.fields['Label']), ['ID', 'Text'])
        self.assertTrue(self.fields['Label']['ID']['is_identifier'])
        self.assertNotIn('ID', self.fields['WavelengthRange'])


class GeneratedProfileTest(unittest.TestCase):
    """models/imaging.metaseed.yaml, generated from the master model."""

    @classmethod
    def setUpClass(cls):
        cls.generator = MetaseedGenerator(MODEL_FILE)
        cls.profile = cls.generator.generate()
        cls.entities = cls.profile['entities']

    def test_committed_profile_up_to_date(self):
        with open(PROFILE_FILE, encoding='utf-8') as file:
            committed = yaml.safe_load(file)
        self.assertEqual(committed, self.profile, 'rerun `python src/main.py metaseed`')

    def test_every_concrete_class_reachable(self):
        concrete = {name for name, cls in self.generator.classes.items() if not cls.abstract and not cls.mixin}
        self.assertEqual(concrete - set(self.entities), UNREACHABLE)


if __name__ == '__main__':
    unittest.main()

import collections
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
from ProfileConverter import ProfileConverter


MODEL_FILE = os.path.join(REPO_ROOT, 'models', 'imaging.yaml')
PROFILE_FILE = os.path.join(REPO_ROOT, 'models', 'imaging.metaseed.yaml')
JSON_SCHEMA_FILE = os.path.join(REPO_ROOT, 'models', 'fullSchema.json')
XSD_FILE = os.path.join(REPO_ROOT, 'models', 'LiMi_XMLSchema.xsd')

# The LiMi XSD references a LightSensor (LightSensorRef) but no element contains one.
UNREACHABLE = {'LightSensor'}

# What the fullSchema.json-based profile has that the generated one holds differently
OLD_FIELD_NAMES = {'Description': 'Annotation'}  # the JSON's name for AnnotationRef
OLD_ONLY = {
    'Tier': 'a constant of each class: an annotation in the model, no dataset field',
    'Image.InstrumentName': 'readonly display of the referenced Instrument',
    'Image.InstrumentID': 'readonly; Image.Instrument holds the ID',
    'Pump': 'the XSD Pump element is a LaserRef: the Laser.Pump reference',
}
ROLE_PREFIXES = ('Transmitted_LightSource_', 'Fluorescence_LightSource_')

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
        concrete = {name for name, cls in self.generator.classes.items() if not cls.abstract}
        self.assertEqual(concrete - set(self.entities), UNREACHABLE)

    def test_holds_everything_of_the_fullschema_json_profile(self):
        old = ProfileConverter(JSON_SCHEMA_FILE, XSD_FILE).convert()['entities']
        new = {name: {field['name']: field for field in entity['fields']} for name, entity in self.entities.items()}
        entity_map = self._map_entities(old, new)
        missing = []
        for old_name, entity in old.items():
            new_name = entity_map.get(old_name, old_name if old_name in new else None)
            if new_name is None and old_name not in OLD_ONLY:
                missing.append(old_name)
            for field in entity['fields'] if new_name else []:
                name = self._new_field_name(field['name'])
                if name not in new[new_name] and field['name'] not in OLD_ONLY \
                        and f'{old_name}.{field["name"]}' not in OLD_ONLY:
                    missing.append(f'{old_name}.{field["name"]} -> {new_name}.{name}')
        self.assertEqual(missing, [])

    @staticmethod
    def _new_field_name(name):
        for prefix in ROLE_PREFIXES:
            name = name.removeprefix(prefix)
        return OLD_FIELD_NAMES.get(name, name)

    def _map_entities(self, old, new):
        """Old entity -> new, following the nesting from the root: the old per-parent copies
        (CMOS_WavelengthRange) map to what the new parent nests there (ComponentWavelengthRange)."""
        entity_map = {self.profile['root_entity']: self.profile['root_entity']}
        queue = collections.deque([self.profile['root_entity']])
        while queue:
            old_parent = queue.popleft()
            for field in old[old_parent]['fields']:
                new_field = new[entity_map[old_parent]].get(self._new_field_name(field['name']))
                child = field.get('items')
                if child in old and child not in entity_map and new_field is not None and new_field.get('items') in new:
                    entity_map[child] = new_field['items']
                    queue.append(child)
        return entity_map


if __name__ == '__main__':
    unittest.main()

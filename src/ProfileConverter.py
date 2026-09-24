"""Convert the LiMi JSON schemas into a metaseed profile specification (YAML).

The JSON schemas (models/fullSchema.json) define each entity's fields but not
which entity contains which; that containment comes from the XSD
(models/LiMi_XMLSchema.xsd), whose element names are the JSON titles.
"""

import collections
import json
import xml.etree.ElementTree as ET

import yaml

DEFAULT_JSON_SCHEMA_FILE = 'models/fullSchema.json'
DEFAULT_XSD_FILE = 'models/LiMi_XMLSchema.xsd'
DEFAULT_PROFILE_FILE = 'models/fullSchema.yaml'

ROOT_ENTITY = 'OME'
PROPERTY_ENTITY = 'Property'
SOURCE_FILE_ENTITY = 'SourceFile'
SOURCE_MAPPING_ENTITY = 'SourceMapping'
CUSTOM_PROPERTIES_ANCHORS = ('OME', 'Image', 'Instrument')
TYPE_MAP = {'number': 'float'}

XS = '{http://www.w3.org/2001/XMLSchema}'


class XsdContainment:
    """Child elements of each global XSD element, with substitution groups expanded to their concrete members."""

    def __init__(self, filename):
        root = ET.parse(filename).getroot()
        self.elements = {e.get('name'): e for e in root.findall(XS + 'element')}
        self.types = {t.get('name'): t for t in root.findall(XS + 'complexType')}
        self.substitutes = collections.defaultdict(list)
        for element in root.findall(XS + 'element'):
            if element.get('substitutionGroup'):
                self.substitutes[element.get('substitutionGroup')].append(element.get('name'))

    def children(self, name):
        """(child element name, maxOccurs) pairs declared inside element `name`."""
        if name not in self.elements:
            return []
        element = self.elements[name]
        declarations = self._declarations(element, frozenset())
        if _local(element.get('type')) in self.types:
            declarations += self._type_declarations(_local(element.get('type')), frozenset())
        return [(member, max_occurs) for child, max_occurs in declarations for member in self._concrete(child)]

    def _concrete(self, name):
        element = self.elements.get(name)
        members = [] if element is not None and element.get('abstract') == 'true' else [name]
        for substitute in self.substitutes.get(name, []):
            members += self._concrete(substitute)
        return members

    def _declarations(self, node, seen_types):
        declarations = []
        for child in node:
            tag = child.tag.replace(XS, '')
            if tag == 'element':
                declarations.append((_local(child.get('name') or child.get('ref')), child.get('maxOccurs', '1')))
            elif tag in ('extension', 'restriction') and _local(child.get('base')) in self.types:
                declarations += self._type_declarations(_local(child.get('base')), seen_types)
                declarations += self._declarations(child, seen_types)
            elif tag != 'annotation':
                declarations += self._declarations(child, seen_types)
        return declarations

    def _type_declarations(self, type_name, seen_types):
        if type_name in seen_types:
            return []
        return self._declarations(self.types[type_name], seen_types | {type_name})


def _local(name):
    return name.split(':')[-1] if name else name


class ProfileConverter:
    def __init__(self, json_schema_filename=DEFAULT_JSON_SCHEMA_FILE, xsd_filename=DEFAULT_XSD_FILE):
        with open(json_schema_filename, encoding='utf-8') as file:
            self.schemas = json.load(file)
        self.containment = XsdContainment(xsd_filename)
        self.title_counts = collections.Counter(s['title'] for s in self.schemas)
        self.entity_names = {self._entity_name(s) for s in self.schemas}
        self.link_targets = {}
        for schema in self.schemas:
            self.link_targets[self._id_stem(schema)] = self._entity_name(schema)
            if self.title_counts[schema['title']] == 1:
                self.link_targets[schema['title']] = schema['title']
        self.entities = {}
        self.unresolved_links = collections.Counter()
        self.containment_fields_added = 0

    def convert(self, name='LiMi', version='2.1'):
        for schema in self.schemas:
            self._add_entity(self._entity_name(schema), schema.get('description'), schema['properties'],
                             schema.get('required', []))
        self._add_root_entity()
        self._add_containment()
        self._add_provenance_entities()
        return {
            'name': name,
            # metaseed wants version as a string; unquoted 2.1 in YAML would be read as a number
            'version': str(version),
            'description': 'Microscopy metadata profile converted from models/fullSchema.json',
            'root_entity': ROOT_ENTITY,
            'entities': self.entities,
        }

    @staticmethod
    def _id_stem(schema):
        return schema['ID'].removesuffix('.json')

    def _entity_name(self, schema):
        return schema['title'] if self.title_counts[schema['title']] == 1 else self._id_stem(schema)

    def _add_entity(self, name, description, properties, required):
        assert name not in self.entities, name
        entity = {}
        if description:
            entity['description'] = description.strip()
        self.entities[name] = entity
        self.entity_names.add(name)
        entity['fields'] = [self._make_field(n, p, n in required, name) for n, p in properties.items()]

    def _make_field(self, name, prop, required, owner):
        field = {'name': name}
        multiple = prop.get('type') == 'array'
        target = prop['items'] if multiple else prop
        if multiple and 'properties' in target:
            sub_name = f'{owner}_{name}'
            self._add_entity(sub_name, prop.get('description'), target['properties'], target.get('required', []))
            item_type, owns = sub_name, True
        elif 'linkTo' in target and target['linkTo'] in self.link_targets:
            item_type, owns = self.link_targets[target['linkTo']], False
        else:
            if 'linkTo' in target:
                self.unresolved_links[target['linkTo']] += 1
            item_type, owns = TYPE_MAP.get(target.get('type'), target.get('type', 'string')), False
        is_entity = item_type in self.entity_names
        if multiple:
            field['type'] = 'list'
        elif is_entity:
            field['type'] = 'entity'
        else:
            field['type'] = item_type
        field['required'] = required
        description = prop.get('description') or target.get('description')
        if description and description != 'NA':
            field['description'] = description.strip()
        if multiple or is_entity:
            field['items'] = item_type
        if owns:
            field['owns'] = True
        if name == 'ID':
            field['is_identifier'] = True
        if 'enum' in target:
            field['constraints'] = {'enum': [str(v) for v in target['enum']]}
        if 'default' in target:
            # metaseed has no default; keep the value as an example rather than drop it
            field['example'] = target['default']
        return field

    def _add_root_entity(self):
        self.entities[ROOT_ENTITY] = {
            'description': 'Top-level container, mirroring the OME root element of models/LiMi_XMLSchema.xsd.',
            'fields': [
                {'name': 'ID', 'type': 'string', 'required': True,
                 'description': 'A unique identifier for this document.', 'is_identifier': True},
                {'name': 'Name', 'type': 'string', 'required': False,
                 'description': 'A user assigned name for this document.'},
            ],
        }

    def _add_provenance_entities(self):
        # Source metadata the profile does not model is kept rather than dropped: as Property records under
        # the nearest anchor, each naming its original source path, and every Image records the files it came from.
        self.entities[PROPERTY_ENTITY] = {
            'description': 'A source metadata value the profile does not model, kept so no metadata is lost.',
            'fields': [
                {'name': 'ID', 'type': 'string', 'required': True,
                 'description': 'A unique identifier for this property.', 'is_identifier': True},
                {'name': 'Name', 'type': 'string', 'required': True,
                 'description': 'The full path of this value in its source file, e.g. "Beam.SpotIndex".'},
                {'name': 'Value', 'type': 'string', 'required': True,
                 'description': 'The value, JSON-encoded so its type is kept (e.g. 1, "1", true, null).'},
                {'name': 'SchemaPath', 'type': 'string', 'required': False,
                 'description': 'Where the value was mapped in the consolidated schema, '
                                'e.g. "ElectronBeam.WorkingDistance.Value".'},
                {'name': 'Unit', 'type': 'string', 'required': False,
                 'description': 'The unit of the value, where the source states one.'},
                {'name': 'Source', 'type': 'string', 'required': False,
                 'description': 'The ID of the SourceFile this value came from.'},
            ],
        }
        self.entities[SOURCE_FILE_ENTITY] = {
            'description': 'A file this metadata was read from, identified by its checksum.',
            'fields': [
                {'name': 'ID', 'type': 'string', 'required': True,
                 'description': 'A unique identifier for this source file.', 'is_identifier': True},
                {'name': 'Name', 'type': 'string', 'required': True, 'description': 'The file name.'},
                {'name': 'Checksum', 'type': 'string', 'required': True,
                 'description': 'The SHA-256 checksum of the file, as lowercase hex.',
                 'constraints': {'pattern': '^[0-9a-f]{64}$'}},
                {'name': 'Format', 'type': 'string', 'required': False,
                 'description': 'The file format, e.g. json or ome-tiff.'},
                {'name': 'Mapping', 'type': 'list', 'required': False,
                 'description': 'Where each value from this file that fits a profile field was placed.',
                 'items': SOURCE_MAPPING_ENTITY, 'owns': True},
            ],
        }
        self.entities[SOURCE_MAPPING_ENTITY] = {
            'description': 'The source key of a value placed in a profile field, so key names are never lost.',
            'fields': [
                {'name': 'ID', 'type': 'string', 'required': True,
                 'description': 'A unique identifier for this mapping.', 'is_identifier': True},
                {'name': 'Field', 'type': 'string', 'required': True,
                 'description': 'The path of the value in this dataset, e.g. "Image[0].Pixels.PhysicalSizeX".'},
                {'name': 'Source', 'type': 'string', 'required': True,
                 'description': 'The full path of the value in its source file.'},
            ],
        }
        for anchor in CUSTOM_PROPERTIES_ANCHORS:
            self._insert_before_tier(anchor, {
                'name': 'CustomProperties', 'type': 'list', 'required': False,
                'description': 'Source metadata values the profile does not model.', 'items': PROPERTY_ENTITY,
                'owns': True})
        self._insert_before_tier('Image', {
            'name': 'SourceFile', 'type': 'list', 'required': False,
            'description': "The files this Image's metadata was read from.", 'items': SOURCE_FILE_ENTITY,
            'owns': True})

    def _insert_before_tier(self, entity, field):
        fields = self.entities[entity]['fields']
        assert all(f['name'] != field['name'] for f in fields), (entity, field['name'])
        fields.insert(next((i for i, f in enumerate(fields) if f['name'] == 'Tier'), len(fields)), field)

    def _add_containment(self):
        # A title shared by several schemas (e.g. Filament as Fluorescence_ and Transmitted_ light source) stands
        # for all of them in the XSD.
        xsd_to_entities = collections.defaultdict(list)
        for schema in self.schemas:
            xsd_to_entities[schema['title']].append(self._entity_name(schema))
        xsd_to_entities[ROOT_ENTITY] = [ROOT_ENTITY]

        for xsd_parent, parent_names in xsd_to_entities.items():
            for xsd_child, max_occurs in self.containment.children(xsd_parent):
                for child in xsd_to_entities.get(xsd_child, []):
                    for parent in parent_names:
                        self._add_containment_field(parent, xsd_child, child, max_occurs)

    def _add_containment_field(self, parent, xsd_child, child, max_occurs):
        fields = self.entities[parent]['fields']
        # A same-named field is the JSON's own rendering of this XSD child (a nested entity, or e.g. a profile
        # file flattened to its location string) and takes precedence.
        existing = next((f for f in fields if f['name'] in (xsd_child, child)), None)
        if existing is None:
            field = {'name': child, 'type': 'list' if max_occurs != '1' else 'entity', 'required': False,
                     'description': self.entities[child].get('description', '').split('. ')[0], 'items': child,
                     'owns': True}
            self._insert_before_tier(parent, field)
            self.containment_fields_added += 1
        elif existing.get('items') == child:
            existing['owns'] = True


def write_profile(profile, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        yaml.safe_dump(profile, file, sort_keys=False, allow_unicode=True, width=120)

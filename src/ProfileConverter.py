"""Convert the LiMi JSON schemas into a metaseed profile specification (YAML).

The JSON schemas (models/fullSchema.json) define each entity's fields but not
which entity contains which; that containment comes from the XSD
(models/LiMi_XMLSchema.xsd), whose element names are the JSON titles.

ProfileExtender derives a second profile, the LiMi one plus what the mapper's
extended schema tree (mappings/schema.extended.json) adds beyond its LiMi tree
(mappings/schema.json), so mapped values outside LiMi get typed fields too.
"""

import collections
import copy
import json
import xml.etree.ElementTree as ET

import yaml

DEFAULT_JSON_SCHEMA_FILE = 'models/fullSchema.json'
DEFAULT_XSD_FILE = 'models/LiMi_XMLSchema.xsd'
DEFAULT_PROFILE_FILE = 'models/fullSchema.yaml'
DEFAULT_EXTENDED_PROFILE_FILE = 'models/schema.extended.yaml'
DEFAULT_SCHEMA_TREE_FILE = 'mappings/schema.json'
DEFAULT_EXTENDED_SCHEMA_TREE_FILE = 'mappings/schema.extended.json'

ROOT_ENTITY = 'OME'
PROPERTY_ENTITY = 'Property'
SOURCE_FILE_ENTITY = 'SourceFile'
SOURCE_MAPPING_ENTITY = 'SourceMapping'
CUSTOM_PROPERTIES_ANCHORS = ('OME', 'Image', 'Instrument')
TYPE_MAP = {'number': 'float'}
# metaseed has no free-form object type; such values do not fit a string field, so they stay Property records
EXTENDED_TREE_TYPES = {'string': 'string', 'number': 'float', 'integer': 'integer', 'boolean': 'boolean',
                       'object': 'string'}

XS = '{http://www.w3.org/2001/XMLSchema}'


class XsdContainment:
    """Child elements of each global XSD element, with substitution groups expanded to their concrete members."""

    def __init__(self, filename):
        root = ET.parse(filename).getroot()
        self.elements = {element.get('name'): element for element in root.findall(XS + 'element')}
        self.types = {type_node.get('name'): type_node for type_node in root.findall(XS + 'complexType')}
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
        self.title_counts = collections.Counter(schema['title'] for schema in self.schemas)
        self.entity_names = {self._entity_name(schema) for schema in self.schemas}
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
            'description': f'Microscopy metadata profile converted from models/fullSchema.json '
                           f'(LiMi model version {", ".join(self._model_versions())})',
            'root_entity': ROOT_ENTITY,
            'entities': self.entities,
        }

    def _model_versions(self):
        # LiMi versions are x.yy.z, which metaseed's MAJOR.MINOR profile version can't hold
        return sorted({schema['modelVersion'] for schema in self.schemas if 'modelVersion' in schema})

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
        # Tier is a constant of the schema, not something a source file states, so a dataset can't be faulted for it
        entity['fields'] = [self._make_field(field_name, prop, field_name in required and field_name != 'Tier', name)
                            for field_name, prop in properties.items()]

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
            field['constraints'] = {'enum': [str(option) for option in target['enum']]}
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
                {'name': 'DerivedFrom', 'type': 'list', 'items': 'string', 'required': False,
                 'description': 'For a value combined from several source values (e.g. a date and a time), '
                                'their source paths.'},
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
                {'name': 'DerivedFrom', 'type': 'list', 'items': 'string', 'required': False,
                 'description': 'For a value combined from several source values (e.g. a date and a time), '
                                'their source paths.'},
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
        assert all(other['name'] != field['name'] for other in fields), (entity, field['name'])
        fields.insert(next((index for index, other in enumerate(fields) if other['name'] == 'Tier'), len(fields)), field)

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
        existing = next((field for field in fields if field['name'] in (xsd_child, child)), None)
        if existing is None:
            field = {'name': child, 'type': 'list' if max_occurs != '1' else 'entity', 'required': False,
                     'description': self.entities[child].get('description', '').split('. ')[0], 'items': child,
                     'owns': True}
            self._insert_before_tier(parent, field)
            self.containment_fields_added += 1
        elif existing.get('items') == child:
            existing['owns'] = True


class ProfileExtender:
    """Extends a profile with what the mapper's extended schema tree adds beyond its LiMi schema tree.

    Additions to a profile entity go on that entity (Instrument.Manufacturer);
    a category that is no profile entity (Detector) becomes a group entity,
    and a group schema.json lacks altogether (ElectronBeam) one under the
    root, where it is top level in the tree. Nested groups become entities
    named by their path (ElectronBeam_WorkingDistance), since names like "X"
    and "Value" recur. A field the profile already has is never replaced.
    """

    def __init__(self, profile, extended_tree, base_tree):
        self.profile = copy.deepcopy(profile)
        self.base_entities = set(profile['entities'])
        self.entities = self.profile['entities']
        self.extended_tree = extended_tree
        self.base_tree = base_tree
        self.added_entities = []
        self.added_fields = []
        self.skipped = []

    def extend(self, name, description):
        self._extend(self.extended_tree, self.base_tree, '', ROOT_ENTITY)
        self.profile['name'] = name
        self.profile['description'] = description
        return self.profile

    def _extend(self, extended_node, base_node, path, owner):
        for key, value in extended_node.items():
            sub_path = f'{path}.{key}' if path else key
            base_value = base_node.get(key) if isinstance(base_node, dict) else None
            if isinstance(value, dict) and key in self.base_entities:
                self._extend(value, base_value or {}, sub_path, key)
            elif isinstance(value, dict) and base_value is not None:
                self._extend(value, base_value, sub_path, _Group(owner, key, sub_path))
            elif base_value is None:
                self._add_field(self._resolve(owner), key, value, sub_path)

    def _resolve(self, owner):
        """The entity name of `owner`, creating a group's entity (and its parent's) on first use."""
        if not isinstance(owner, _Group):
            return owner
        name = owner.path.replace('.', '_')
        if name not in self.entities:
            self._add_field(self._resolve(owner.parent), owner.key, {}, owner.path)
        return name

    def _add_field(self, entity, name, value, path):
        fields = self.entities[entity]['fields']
        if any(field['name'] == name for field in fields):
            self.skipped.append(f'{entity}.{name} (already a profile field) <- {path}')
            return
        tier = next((index for index, field in enumerate(fields) if field['name'] == 'Tier'), len(fields))
        description = f'From the extended schema ({path}).'
        if isinstance(value, dict):
            child = path.replace('.', '_')
            assert child not in self.entities, child
            # every LiMi entity has an ID as identifier; optional here, since no source states one for these groups
            self.entities[child] = {'description': description, 'fields': [
                {'name': 'ID', 'type': 'string', 'required': False,
                 'description': 'A unique identifier for this component.', 'is_identifier': True}]}
            self.added_entities.append(child)
            fields.insert(tier, {'name': name, 'type': 'entity', 'required': False, 'description': description,
                                 'items': child, 'owns': True})
            for key, sub in value.items():
                self._add_field(child, key, sub, f'{path}.{key}')
        elif value == 'array':
            fields.insert(tier, {'name': name, 'type': 'list', 'required': False, 'description': description,
                                 'items': 'string'})
        else:
            fields.insert(tier, {'name': name, 'type': EXTENDED_TREE_TYPES[value], 'required': False,
                                 'description': description})
        self.added_fields.append(f'{entity}.{name}')


class _Group:
    """A category of the schema tree that is no profile entity, made an entity once something lands in it."""

    def __init__(self, parent, key, path):
        self.parent = parent
        self.key = key
        self.path = path


def write_profile(profile, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        yaml.safe_dump(profile, file, sort_keys=False, allow_unicode=True, width=120)

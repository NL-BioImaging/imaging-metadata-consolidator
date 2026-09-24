"""Export converted metadata as a metaseed dataset of the LiMi profile.

Takes AcquisitionMetadataMapper output (the consolidated category -> entity
-> field tree plus its SourceMap) and builds one OME document for the
profile in models/fullSchema.yaml. A value goes into a typed profile field
only if it fits exactly; anything else becomes a Property record holding its
source path and JSON-encoded value, so no metadata is lost. Every value
placed in a typed field gets a SourceMapping record on the SourceFile, so its
source key is kept too.
"""

import collections
import hashlib
import json
import os.path
import re

import yaml

from AcquisitionMetadataMapper import SOURCE_MAP_KEY, leaf_suffixes
from ProfileConverter import (CUSTOM_PROPERTIES_ANCHORS, DEFAULT_PROFILE_FILE, PROPERTY_ENTITY, ROOT_ENTITY,
                              SOURCE_FILE_ENTITY, SOURCE_MAPPING_ENTITY)

PROVENANCE_ENTITIES = (PROPERTY_ENTITY, SOURCE_FILE_ENTITY, SOURCE_MAPPING_ENTITY)


def file_checksum(filename):
    with open(filename, 'rb') as file:
        return hashlib.sha256(file.read()).hexdigest()


class DatasetExporter:
    def __init__(self, profile_filename=DEFAULT_PROFILE_FILE):
        with open(profile_filename, encoding='utf-8') as file:
            profile = yaml.safe_load(file)
        self.entities = {name: {f['name']: f for f in entity['fields']}
                         for name, entity in profile['entities'].items()}
        self.paths = self._shortest_paths()

    def _nested_entity(self, field):
        if field['type'] in ('entity', 'list') and field.get('items') in self.entities:
            return field['items']
        return None

    def _shortest_paths(self):
        """Each reachable entity's first shortest path from the root, as (field, entity, is_list) steps."""
        paths = {ROOT_ENTITY: []}
        queue = collections.deque([ROOT_ENTITY])
        while queue:
            parent = queue.popleft()
            for field in self.entities[parent].values():
                child = self._nested_entity(field)
                if child is not None and child not in paths and child not in PROVENANCE_ENTITIES:
                    paths[child] = paths[parent] + [(field['name'], child, field['type'] == 'list')]
                    queue.append(child)
        return paths

    def export(self, converted, source_name, checksum, file_format=None):
        """Build the OME dataset for one converted source file."""
        export = _Export(self, converted[SOURCE_MAP_KEY])
        image = export.instance_at(self.paths['Image'])
        source_file = {'ID': 'SourceFile:0', 'Name': source_name, 'Checksum': checksum}
        if file_format:
            source_file['Format'] = file_format
        image.node.setdefault('SourceFile', []).append(source_file)
        export.source_file = source_file
        export.walk({key: value for key, value in converted.items() if key != SOURCE_MAP_KEY}, '', None,
                    export.root)
        if export.mappings:
            source_file['Mapping'] = export.mappings
        return export.root.node


class _Instance:
    def __init__(self, entity, node, path, anchor):
        self.entity = entity
        self.node = node
        self.path = path
        self.anchor = anchor if anchor is not None else self

    def child_path(self, field, index=None):
        path = f'{self.path}.{field}' if self.path else field
        return path if index is None else f'{path}[{index}]'


class _Export:
    def __init__(self, exporter, source_map):
        self.exporter = exporter
        self.source_map = source_map
        self.root = _Instance(ROOT_ENTITY, {'ID': 'OME:0'}, '', None)
        self.mappings = []
        self.property_count = 0
        self.source_file = None

    def child(self, parent, field, entity, is_list, index=0):
        """The `index`-th instance of `entity` in `parent`'s `field`, created if absent."""
        if is_list:
            items = parent.node.setdefault(field, [])
            while len(items) <= index:
                items.append({})
            node, path = items[index], parent.child_path(field, index)
        else:
            node, path = parent.node.setdefault(field, {}), parent.child_path(field)
        return _Instance(entity, node, path, None if entity in CUSTOM_PROPERTIES_ANCHORS else parent.anchor)

    def instance_at(self, steps, index=0):
        instance = self.root
        for position, (field, entity, is_list) in enumerate(steps):
            instance = self.child(instance, field, entity, is_list, index if position == len(steps) - 1 else 0)
        return instance

    def entity_named(self, key, parent_key):
        paths = self.exporter.paths
        combined = f'{parent_key}_{key}'
        return combined if combined in paths else key if key in paths else None

    def walk(self, node, path, parent_key, anchor_only, instance=None):
        """Place every entry of `node` (at mapper output `path`): in `instance`'s fields, a new entity, or a Property."""
        for key, value in node.items():
            converted_path = f'{path}.{key}' if path else str(key)
            field = self.exporter.entities[instance.entity].get(key) if instance is not None else None
            entity = self.entity_named(key, parent_key)
            is_record = isinstance(value, dict) and value
            is_record_list = isinstance(value, list) and value and all(isinstance(v, dict) and v for v in value)
            nested = self.exporter._nested_entity(field) if field is not None else None
            if nested is not None and (is_record or (is_record_list and field['type'] == 'list')):
                records = value if is_record_list else [value]
                for index, record in enumerate(records):
                    child = self.child(instance, key, nested, field['type'] == 'list', index)
                    item_path = f'{converted_path}[{index}]' if is_record_list else converted_path
                    self.walk(record, item_path, key, child.anchor, child)
            elif field is not None and nested is None and key not in instance.node and fits(value, field):
                instance.node[key] = value
                self.add_mapping(instance.child_path(key), converted_path)
            elif field is None and entity is not None and (is_record or is_record_list):
                records = value if is_record_list else [value]
                for index, record in enumerate(records):
                    target = self.instance_at(self.exporter.paths[entity], index)
                    item_path = f'{converted_path}[{index}]' if is_record_list else converted_path
                    self.walk(record, item_path, key, target.anchor, target)
            elif field is None and is_record:
                self.walk(value, converted_path, key, anchor_only)
            elif field is None and is_record_list:
                for index, record in enumerate(value):
                    self.walk(record, f'{converted_path}[{index}]', key, anchor_only)
            else:
                self.add_properties(anchor_only, converted_path, value)

    def add_mapping(self, dataset_path, converted_path):
        self.mappings.append({'ID': f'SourceMapping:{len(self.mappings)}', 'Field': dataset_path,
                              'Source': self.source_map[converted_path]})

    def add_properties(self, anchor, converted_path, value):
        properties = anchor.node.setdefault('CustomProperties', [])
        for suffix in leaf_suffixes(value):
            leaf_path = f'{converted_path}{suffix}'
            leaf = _value_at(value, suffix)
            record = {'ID': f'Property:{self.property_count}', 'Name': self.source_map[leaf_path],
                      'Value': json.dumps(leaf, ensure_ascii=False)}
            if leaf_path != record['Name']:
                record['SchemaPath'] = leaf_path
            record['Source'] = self.source_file['ID']
            properties.append(record)
            self.property_count += 1


def _value_at(value, suffix):
    for part in re.findall(r'\.([^.\[]+)|\[(\d+)\]', suffix):
        value = value[part[0]] if part[0] else value[int(part[1])]
    return value


def fits(value, field):
    """Whether `value` can go into `field` as is, so that nothing about it changes."""
    field_type = field['type']
    if field_type == 'list':
        return isinstance(value, list) and all(fits(item, {'type': field.get('items', 'string')}) for item in value)
    constraints = field.get('constraints', {})
    fits_type = {
        'string': isinstance(value, str),
        'integer': isinstance(value, int) and not isinstance(value, bool),
        'float': isinstance(value, (int, float)) and not isinstance(value, bool),
        'boolean': isinstance(value, bool),
    }.get(field_type, False)
    fits_enum = 'enum' not in constraints or (isinstance(value, str) and value in constraints['enum'])
    fits_pattern = ('pattern' not in constraints
                    or (isinstance(value, str) and re.fullmatch(constraints['pattern'], value) is not None))
    return fits_type and fits_enum and fits_pattern


def export_file(source_file, output_file, mapper, exporter):
    """Convert one source file and write its dataset to `output_file`; returns the dataset."""
    from convert import read_metadata, write_metadata
    converted = mapper.convert_metadata(read_metadata(source_file))
    file_format = os.path.splitext(source_file)[1].lstrip('.').lower() or None
    dataset = exporter.export(converted, os.path.basename(source_file), file_checksum(source_file), file_format)
    write_metadata(dataset, output_file)
    return dataset

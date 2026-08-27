import os.path
import re

from file.json_serialisation import deserialise_json
from file.yaml_serialisation import deserialise_yaml
from helper import create_source


class Consolidator:
    def __init__(self):
        self.raw_schema = {}
        self.schema = {}
        self.key_style = None
        self.type_descriptions = {}
        self.datasets = []

    def import_schema(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        if ext == '.json':
            import json
            with open(filename, 'r', encoding='utf-8') as f:
                schema = json.load(f)
            id_key = 'title'
            child_key = 'properties'
            type_key = 'type'
            category_key = 'category'
        elif ext in ['.yaml', '.yml']:
            import yaml
            with open(filename, 'r', encoding='utf-8') as f:
                schema = yaml.safe_load(f)
            id_key = 'title'
            child_key = 'attributes'
            type_key = 'range'
            category_key = 'category'
        else:
            raise ValueError(f"Unsupported schema file format: {ext}")
        if isinstance(schema, list):
            if not self.raw_schema:
                self.raw_schema = []
            if not isinstance(self.raw_schema, list):
                raise TypeError('Cannot merge list and mapping schemas')
            self.raw_schema.extend(schema)
        else:
            if isinstance(self.raw_schema, list):
                raise TypeError('Cannot merge mapping and list schemas')
            self.raw_schema |= schema
        self.schema |= assimilate_schema_root(
            schema, id_key, child_key, type_key, category_key
        )
        self.key_style = detect_key_style(self.schema)
        self.type_descriptions = detect_type_descriptions(self.schema)

    def add_dataset(self, filename):
        if os.path.splitext(filename)[1].lower() in ('.json', '.yaml', '.yml'):
            with open(filename, 'r') as file:
                    if filename.endswith('.json'):
                        metadata = deserialise_json(file.read())
                    else:
                        metadata = deserialise_yaml(file.read())
        else:
            source = create_source(filename)
            source.init_metadata()
            metadata = source.get_acquisition_metadata()

        if 'manufacturer' in metadata and metadata['manufacturer']:
            manufacturer = metadata['manufacturer']
        else:
            manufacturer = search_metadata_fully(metadata, ['manufacturer', 'make'],
                                                 contexts=['instrument', 'microscope', 'device', 'system', ''])

        if 'model' in metadata and metadata['model']:
            model = metadata['model']
        else:
            model = search_metadata_fully(metadata, ['model', 'name', 'product', 'productname', 'identifier'],
                                          contexts=['instrument', 'microscope', 'device', 'system', ''])

        if 'serial' in metadata and metadata['serial']:
            serial = metadata['serial']
        else:
            serial = search_metadata_fully(metadata, ['serialnumber', 'serial'],
                                           contexts=['instrument', 'microscope', 'device', 'system', ''])

        self.datasets.append({
            'name': os.path.splitext(os.path.basename(filename))[0],
            'manufacturer': manufacturer,
            'model': model,
            'serial': serial,
            'metadata': metadata,
        })

    def add_data(self, metadata):
        if not isinstance(metadata, dict):
            raise TypeError('Metadata must be a mapping')
        merge_data_schema(metadata, self.schema, self.schema, self.key_style,
                          self.type_descriptions)

    def get_schema(self):
        return self.schema

    def dump(self):
        return {
            'schema': self.schema,
            'datasets': self.datasets,
        }


def search_metadata_fully(metadata, labels, contexts=None):
    for context in contexts:
        for label in labels:
            search_labels = [label]
            if context:
                search_labels.append(context)
            value = search_metadata(metadata, search_labels)
            if value is not None:
                return value
    return None


def search_metadata(metadata, labels):
    for key, value in metadata.items():
        if isinstance(value, dict):
            match = search_metadata(value, labels)
            if match is not None:
                return match
        else:
            key1 = key.lower()
            for label in labels:
                label1 = label.lower()
                if label1 in key1 and not isinstance(value, dict):
                    return value
    return None


def merge_data_schema(metadata, schema, schema_root, key_style,
                      type_descriptions):
    """Merge metadata fields into the closest matching schema branches."""
    for key, value in metadata.items():
        match = find_schema_item(schema, key)
        if match is None and schema is not schema_root:
            match = find_schema_item(schema_root, key)

        if match is not None:
            container, schema_key = match
            schema_value = container[schema_key]
            if isinstance(schema_value, dict):
                merge_data_children(value, schema_value, schema_root, key_style,
                                    type_descriptions)
        else:
            # Source formats commonly add wrapper levels which are absent from
            # the target schema (for example OME around Image).  If descendants
            # can be placed in existing schema branches, omit only that wrapper.
            if isinstance(value, dict) and metadata_matches_schema(value, schema_root):
                merge_data_schema(value, schema, schema_root, key_style,
                                  type_descriptions)
            else:
                schema[format_schema_key(key, key_style)] = infer_data_schema(
                    value, key_style, type_descriptions
                )


def merge_data_children(value, schema, schema_root, key_style,
                        type_descriptions):
    if isinstance(value, dict):
        merge_data_schema(value, schema, schema_root, key_style,
                          type_descriptions)
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                merge_data_schema(item, schema, schema_root, key_style,
                                  type_descriptions)


def find_schema_item(schema, key):
    """Find a key hierarchically, preferring the current branch."""
    if not isinstance(schema, dict):
        return None
    if key in schema:
        return schema, key

    folded_key = normalise_schema_key(key)
    for schema_key in schema:
        if normalise_schema_key(schema_key) == folded_key:
            return schema, schema_key
    for value in schema.values():
        match = find_schema_item(value, key)
        if match is not None:
            return match
    return None


def metadata_matches_schema(metadata, schema):
    for key, value in metadata.items():
        if find_schema_item(schema, key) is not None:
            return True
        if isinstance(value, dict) and metadata_matches_schema(value, schema):
            return True
        if isinstance(value, (list, tuple)):
            if any(isinstance(item, dict) and metadata_matches_schema(item, schema)
                   for item in value):
                return True
    return False


def infer_data_schema(value, key_style, type_descriptions):
    if isinstance(value, dict):
        return {format_schema_key(key, key_style): infer_data_schema(
                    child, key_style, type_descriptions
                )
                for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        inferred = {}
        for item in value:
            if isinstance(item, dict):
                merge_data_schema(item, inferred, inferred, key_style,
                                  type_descriptions)
        return inferred or describe_data_type(value, type_descriptions)
    return describe_data_type(value, type_descriptions)


def normalise_schema_key(key):
    return ''.join(character for character in str(key).casefold()
                   if character.isalnum())


def detect_key_style(schema):
    counts = {'pascal': 0, 'camel': 0, 'snake': 0,
              'upper_snake': 0, 'lower': 0}

    def count_keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                text = str(key)
                if '_' in text and text.upper() == text:
                    counts['upper_snake'] += 1
                elif '_' in text and text.lower() == text:
                    counts['snake'] += 1
                elif text[:1].isupper():
                    counts['pascal'] += 1
                elif any(character.isupper() for character in text[1:]):
                    counts['camel'] += 1
                else:
                    counts['lower'] += 1
                count_keys(value)

    count_keys(schema)
    return max(counts, key=counts.get) if any(counts.values()) else 'preserve'


def format_schema_key(key, style):
    text = str(key)
    words = re.findall(r'[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+',
                       text.replace('-', ' ').replace('_', ' '))
    if not words or style == 'preserve':
        return text
    words = [word.lower() for word in words]
    if style == 'pascal':
        return ''.join(word.capitalize() for word in words)
    if style == 'camel':
        return words[0] + ''.join(word.capitalize() for word in words[1:])
    if style == 'snake':
        return '_'.join(words)
    if style == 'upper_snake':
        return '_'.join(words).upper()
    return ''.join(words)


def detect_type_descriptions(schema):
    aliases = {
        'string': {'string', 'str', 'text'},
        'boolean': {'boolean', 'bool'},
        'integer': {'integer', 'int', 'long'},
        'number': {'number', 'float', 'double', 'decimal'},
        'array': {'array', 'list', 'sequence'},
        'object': {'object', 'dict', 'mapping'},
        'null': {'null', 'none'},
    }
    descriptions = {name: {} for name in aliases}

    def collect(node):
        if isinstance(node, dict):
            for value in node.values():
                collect(value)
        elif isinstance(node, str):
            normalised = node.casefold()
            for name, names in aliases.items():
                if normalised in names:
                    counts = descriptions[name]
                    counts[node] = counts.get(node, 0) + 1

    collect(schema)
    observed = [description for counts in descriptions.values()
                for description in counts]
    if observed and all(description.isupper() for description in observed):
        format_default = str.upper
    elif observed and all(description[:1].isupper() for description in observed):
        format_default = str.capitalize
    else:
        format_default = str.lower

    result = {}
    for name, counts in descriptions.items():
        if counts:
            result[name] = max(counts, key=counts.get)
        else:
            result[name] = format_default(name)
    return result


def describe_data_type(value, type_descriptions):
    type_name = type(value).__name__.casefold()
    if value is None:
        description = 'null'
    elif isinstance(value, bool) or type_name.startswith('bool'):
        description = 'boolean'
    elif isinstance(value, int) or type_name.startswith(('int', 'uint')):
        description = 'integer'
    elif isinstance(value, float) or type_name.startswith(('float', 'double', 'decimal')):
        description = 'number'
    elif isinstance(value, str) or type_name.startswith(('str', 'unicode', 'bytes')):
        description = 'string'
    elif isinstance(value, (list, tuple)):
        description = 'array'
    elif isinstance(value, dict):
        description = 'object'
    else:
        description = type_name
    return type_descriptions.get(description, description)


def assimilate_schema_root(data, id_key, child_key, type_key,
                           category_key='category'):
    if isinstance(data, list):
        schema = {}
        items = []
        item_nodes = {}

        # First create every schema item.  Categories are allowed to name an
        # item which occurs later in the input, so attaching as we iterate is
        # order-dependent.
        for item in data:
            key = item.get(id_key)
            if key is not None:
                node = assimilate_schema(item.get(child_key) or {}, id_key, child_key, type_key)
                items.append((key, item.get(category_key), node))
                item_nodes.setdefault(key, node)

        category_nodes = {}

        def category_node(category):
            """Return an existing item or create the requested category path."""
            if category in item_nodes:
                return item_nodes[category]
            if category in category_nodes:
                return category_nodes[category]

            node = schema
            path = []
            for part in category.split('.'):
                path.append(part)
                name = '.'.join(path)
                if name in item_nodes:
                    child = item_nodes[name]
                else:
                    child = category_nodes.setdefault(name, {})
                node.setdefault(part, child)
                node = child
            return node

        # Then attach all items.  This makes parents and children findable
        # regardless of their order in fullSchema.json.
        for key, category, node in items:
            if not category or category == key:
                schema.setdefault(key, node)
            else:
                category_node(category).setdefault(key, node)

        # A category can refer to a real item which was already added at the
        # root.  Remove that item's root alias once it has its own parent.
        nested_item_names = {key for key, category, _ in items
                             if category and category != key}
        for key in nested_item_names:
            if schema.get(key) is item_nodes.get(key):
                del schema[key]
        return schema
    elif isinstance(data, dict):
        return assimilate_schema(data, id_key, child_key, type_key)
    return {}


def assimilate_schema(data, id_key, child_key, type_key):
    schema = {}
    for key, value in data.items():
        if isinstance(value, dict):
            children = value.get(child_key)
            if children:
                schema[key] = assimilate_schema(children, id_key, child_key, type_key)
            else:
                schema[key] = value.get(type_key)
    return schema

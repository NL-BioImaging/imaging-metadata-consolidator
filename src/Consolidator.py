import os.path


class Consolidator:
    def __init__(self):
        self.schema = {}
        self.datasets = []

    def import_schema(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        if ext == '.json':
            import json
            with open(filename, 'r') as f:
                schema = json.load(f)
            id_key = 'title'
            child_key = 'properties'
            type_key = 'type'
        elif ext in ['.yaml', '.yml']:
            import yaml
            with open(filename, 'r') as f:
                schema = yaml.safe_load(f)
            id_key = 'title'
            child_key = 'attributes'
            type_key = 'range'
        else:
            raise ValueError(f"Unsupported schema file format: {ext}")
        self.raw_schema = schema
        self.schema = assimilate_schema_root(schema, id_key, child_key, type_key)
        pass

    def add(self, name, metadata):
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
            'name': name,
            'manufacturer': manufacturer,
            'model': model,
            'serial': serial,
            'metadata': metadata,
        })

    def consolidate(self):
        consolidated = {}
        for dataset in self.datasets:
            name = dataset['name']
            metadata = dataset['metadata']
            consolidated[name] = dataset
        self.consolidated = consolidated
        return consolidated


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


def assimilate_schema_root(data, id_key, child_key, type_key):
    schema = {}
    if isinstance(data, list):
        for item in data:
            key = item.get(id_key)
            schema[key] = assimilate_schema(item.get(child_key), id_key, child_key, type_key)
    elif isinstance(data, dict):
        schema = assimilate_schema(data, id_key, child_key, type_key)
    return schema


def assimilate_schema(data, id_key, child_key, type_key):
    schema = {}
    for key, value in data.items():
        children = value.get(child_key)
        if children:
            schema[key] |= assimilate_schema(value, id_key, child_key, type_key)
        else:
            schema[key] = value.get(type_key)
    return schema

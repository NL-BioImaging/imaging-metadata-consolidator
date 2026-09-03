"""Map a single source metadata file onto the consolidated schema.

Public API for converting one source metadata file through
AcquisitionMetadataMapper onto the consolidated schema. See main.py for the
CLI entry point that runs this over a folder of source files.
"""

import json
import os.path

from AcquisitionMetadataMapper import (
    AcquisitionMetadataMapper,
    DEFAULT_MAPPINGS_FILE,
    DEFAULT_SCHEMA_FILE,
)


DEFAULT_OUTPUT_FORMAT = '.yaml'


def read_metadata(input_file):
    """Read a metadata dict from `input_file`, choosing JSON or YAML by extension."""
    ext = os.path.splitext(input_file)[1].lower()
    with open(input_file, 'r', encoding='utf-8') as file:
        if ext in ('.yaml', '.yml'):
            import yaml
            return yaml.safe_load(file)
        return json.load(file)


def write_metadata(data, output_file):
    """Write `data` to `output_file`, choosing JSON or YAML by extension."""
    ext = os.path.splitext(output_file)[1].lower()
    os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as file:
        if ext in ('.yaml', '.yml'):
            import yaml
            yaml.dump(data, file, sort_keys=False, allow_unicode=True)
        else:
            json.dump(data, file, indent=2, default=str, ensure_ascii=False)


def convert(input_file, output_file, schema_file=DEFAULT_SCHEMA_FILE,
           mappings_file=DEFAULT_MAPPINGS_FILE):
    """Map a single source metadata file onto the schema, writing to `output_file`.

    Returns the converted dict.
    """
    mapper = AcquisitionMetadataMapper(schema_file, mappings_file)
    metadata = read_metadata(input_file)
    converted = mapper.convert_metadata(metadata)
    write_metadata(converted, output_file)
    return converted


if __name__ == "__main__":
    # load sources and convert to yaml in output folder
    import glob

    for source_file in sorted(glob.glob(os.path.join('sources', '*.json'))):
        name = os.path.splitext(os.path.basename(source_file))[0]
        convert(source_file, os.path.join('output', name + DEFAULT_OUTPUT_FORMAT))

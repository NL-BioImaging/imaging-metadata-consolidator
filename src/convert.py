"""Map a single source metadata file onto the consolidated schema.

Public API for converting one source metadata file through
AcquisitionMetadataMapper onto the consolidated schema. See main.py for the
CLI entry point that runs this over a folder of source files.
"""

import glob
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


def convert_file(input_file, output_file,
                 schema_file=DEFAULT_SCHEMA_FILE,
                 mappings_file=DEFAULT_MAPPINGS_FILE):
    """Map a single source metadata file onto the schema, writing to `output_file`.

    Returns the converted dict.
    """
    mapper = AcquisitionMetadataMapper(schema_file, mappings_file)
    metadata = read_metadata(input_file)
    converted = mapper.convert_metadata(metadata)
    write_metadata(converted, output_file)
    return converted


def convert_files(input_dir, output_dir,
                  schema_file=DEFAULT_SCHEMA_FILE,
                  mappings_file=DEFAULT_MAPPINGS_FILE):
    """Map every source metadata file in `input_dir` onto the schema.

    Builds the mapper once and reuses it across every file, writing each
    converted file into `output_dir`. Returns the list of written output
    file paths.
    """
    mapper = AcquisitionMetadataMapper(schema_file, mappings_file)
    input_files = sorted(
        file for extension in ('.json', '.yaml', '.yml')
        for file in glob.glob(os.path.join(input_dir, f'*{extension}'))
    )

    if not input_files:
        raise FileNotFoundError(f'No input files found in {input_dir}')

    output_files = []
    for input_file in input_files:
        metadata = read_metadata(input_file)
        converted = mapper.convert_metadata(metadata)
        name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir, name + DEFAULT_OUTPUT_FORMAT)
        write_metadata(converted, output_file)
        output_files.append(output_file)
    return output_files


if __name__ == "__main__":
    # load sources and convert to yaml in output folder
    convert_files('sources', 'output')

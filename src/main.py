"""CLI entry point for the imaging metadata consolidator.

Subcommands:
  consolidate  Merge per-source acquisition metadata into a base schema
               (see Consolidator).
  convert      Map per-source acquisition metadata onto the consolidated
               schema (see AcquisitionMetadataMapper).
"""

import argparse
from file.json_serialisation import serialise_json
import glob
import os.path

from AcquisitionMetadataMapper import DEFAULT_MAPPINGS_FILE, DEFAULT_SCHEMA_FILE
from Consolidator import Consolidator
from convert import convert_files


def consolidation(schema_filename, input_filenames):
    consolidator = Consolidator()
    consolidator.import_schema(schema_filename)

    for filename in input_filenames:
        consolidator.add_dataset(filename)

    return consolidator.dump()


def run_consolidate(args):
    input_filenames = sorted(glob.glob(os.path.join(args.input, '*')))
    results = consolidation(args.schema, input_filenames)

    os.makedirs(args.output, exist_ok=True)
    schema_file = os.path.join(args.output, 'schema.json')
    with open(schema_file, 'w') as file:
        file.write(serialise_json(results['schema']))
    print(f'Wrote {schema_file}')

    for dataset in results['datasets']:
        output_file = os.path.join(args.output, dataset['name'] + '.json')
        with open(output_file, 'w') as file:
            file.write(serialise_json(dataset['metadata']))
        print(f'Wrote {output_file}')


def run_convert(args):
    for output_file in convert_files(args.input, args.output, args.schema, args.mappings):
        print(f'Wrote {output_file}')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', required=True)

    consolidate_parser = subparsers.add_parser(
        'consolidate', help='Merge per-source metadata into a base schema')
    consolidate_parser.add_argument('--input', required=True,
                        help='Folder of source acquisition metadata files')
    consolidate_parser.add_argument('--output', required=True,
                        help='Folder to write the consolidated schema and datasets to')
    consolidate_parser.add_argument('--schema', default='models/fullSchema.json',
                        help='Path to the base schema file to consolidate against')
    consolidate_parser.set_defaults(func=run_consolidate)

    convert_parser = subparsers.add_parser(
        'convert', help='Map per-source metadata onto the consolidated schema')
    convert_parser.add_argument('--input', required=True,
                        help='Folder of source metadata files')
    convert_parser.add_argument('--output', required=True,
                        help='Folder to write converted files to')
    convert_parser.add_argument('--schema', default=DEFAULT_SCHEMA_FILE,
                        help='Path to schema.extended.json')
    convert_parser.add_argument('--mappings', default=DEFAULT_MAPPINGS_FILE,
                        help='Path to mappings.json')
    convert_parser.set_defaults(func=run_convert)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()

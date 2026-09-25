"""CLI entry point for the imaging metadata consolidator.

Subcommands:
  consolidate  Merge per-source acquisition metadata into a base schema
               (see Consolidator).
  convert      Map per-source acquisition metadata onto the consolidated
               schema (see AcquisitionMetadataMapper).
  profile      Convert the LiMi JSON schemas into a metaseed profile YAML,
               and a second one extended with the mapper's extended
               schema (see ProfileConverter, ProfileExtender).
  export       Convert source metadata into metaseed datasets of that
               profile (see DatasetExporter).
"""

import argparse
import json
from file.json_serialisation import serialise_json
import glob
import os.path

from AcquisitionMetadataMapper import DEFAULT_MAPPINGS_FILE, DEFAULT_SCHEMA_FILE, AcquisitionMetadataMapper
from Consolidator import Consolidator
from convert import convert_files
from DatasetExporter import DatasetExporter, export_file
from ProfileConverter import (DEFAULT_EXTENDED_PROFILE_FILE, DEFAULT_EXTENDED_SCHEMA_TREE_FILE,
                              DEFAULT_JSON_SCHEMA_FILE, DEFAULT_PROFILE_FILE, DEFAULT_SCHEMA_TREE_FILE, DEFAULT_XSD_FILE,
                              ProfileConverter, ProfileExtender, write_profile)


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


def run_profile(args):
    converter = ProfileConverter(args.schema, args.xsd)
    profile = converter.convert(version=args.version)
    write_profile(profile, args.output)
    print(f'Wrote {args.output}: {len(converter.entities)} entities, '
          f'{converter.containment_fields_added} containment fields added from the XSD')
    if converter.unresolved_links:
        print(f'Links to undefined entities, kept as strings: {dict(converter.unresolved_links)}')
    with open(args.schema_tree, encoding='utf-8') as file:
        base_tree = json.load(file)
    with open(args.extended_schema_tree, encoding='utf-8') as file:
        extended_tree = json.load(file)
    extender = ProfileExtender(profile, extended_tree, base_tree)
    write_profile(extender.extend(f'{profile["name"]}-extended',
                                  f'{profile["description"]}, extended with {args.extended_schema_tree}'),
                  args.extended_output)
    print(f'Wrote {args.extended_output}: {len(extender.added_entities)} entities and '
          f'{len(extender.added_fields)} fields added from {args.extended_schema_tree}')
    for skipped in extender.skipped:
        print(f'  skipped {skipped}')


def run_export(args):
    mapper = AcquisitionMetadataMapper(args.schema, args.mappings)
    exporter = DatasetExporter(args.profile)
    input_files = sorted(glob.glob(os.path.join(args.input, '*.json')))
    if not input_files:
        raise FileNotFoundError(f'No input files found in {args.input}')
    for input_file in input_files:
        name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(args.output, name + '.yaml')
        export_file(input_file, output_file, mapper, exporter)
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

    profile_parser = subparsers.add_parser(
        'profile', help='Convert the LiMi JSON schemas into a metaseed profile YAML')
    profile_parser.add_argument('--schema', default=DEFAULT_JSON_SCHEMA_FILE,
                        help='Path to the LiMi JSON schemas (fullSchema.json)')
    profile_parser.add_argument('--xsd', default=DEFAULT_XSD_FILE,
                        help='Path to the LiMi XSD, which defines the entity containment')
    profile_parser.add_argument('--output', default=DEFAULT_PROFILE_FILE,
                        help='Path to write the profile YAML to')
    profile_parser.add_argument('--version', default='2.1',
                        help='Profile version, in x.y format')
    profile_parser.add_argument('--extended-output', default=DEFAULT_EXTENDED_PROFILE_FILE,
                        help='Path to write the profile extended with the extended schema tree to')
    profile_parser.add_argument('--schema-tree', default=DEFAULT_SCHEMA_TREE_FILE,
                        help="Path to the mapper's LiMi schema tree (schema.json)")
    profile_parser.add_argument('--extended-schema-tree', default=DEFAULT_EXTENDED_SCHEMA_TREE_FILE,
                        help="Path to the mapper's extended schema tree (schema.extended.json)")
    profile_parser.set_defaults(func=run_profile)

    export_parser = subparsers.add_parser(
        'export', help='Convert source metadata into metaseed datasets of the profile')
    export_parser.add_argument('--input', required=True,
                        help='Folder of source metadata files')
    export_parser.add_argument('--output', required=True,
                        help='Folder to write the datasets to')
    export_parser.add_argument('--profile', default=DEFAULT_PROFILE_FILE,
                        help='Path to the profile YAML')
    export_parser.add_argument('--schema', default=DEFAULT_SCHEMA_FILE,
                        help='Path to schema.extended.json')
    export_parser.add_argument('--mappings', default=DEFAULT_MAPPINGS_FILE,
                        help='Path to mappings.json')
    export_parser.set_defaults(func=run_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()

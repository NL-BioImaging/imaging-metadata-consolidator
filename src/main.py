"""CLI entry point for the imaging metadata consolidator.

Subcommands:
  consolidate  Merge per-source acquisition metadata into a base schema
               (see Consolidator).
  convert      Map per-source acquisition metadata onto the imaging model
               (see AcquisitionMetadataMapper).
  export       Convert source metadata into metaseed datasets of the
               profile generated from the model (see DatasetExporter).
  linkml       Create the LinkML master model (models/imaging.yaml) from the
               LiMi XSD, once (see LinkmlConverter).
  metaseed     Generate a metaseed profile from the LinkML master model
               (see MetaseedGenerator).
"""

import argparse
from file.json_serialisation import serialise_json
import glob
import os.path

from AcquisitionMetadataMapper import DEFAULT_MAPPINGS_FILE, DEFAULT_SCHEMA_FILE, AcquisitionMetadataMapper
from Consolidator import Consolidator
from convert import convert_files
from DatasetExporter import DatasetExporter, export_file
from LinkmlConverter import (DEFAULT_LINKML_FILE, DEFAULT_OME_XSD_FILE, DEFAULT_UNITS_FILE, DEFAULT_XSD_FILE,
                             LinkmlConverter, write_schema)
from MetaseedGenerator import DEFAULT_PROFILE_FILE as DEFAULT_METASEED_FILE, MetaseedGenerator
from MetaseedGenerator import write_profile as write_metaseed_profile


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


def run_linkml(args):
    # the model is edited by hand once created; regenerating it would discard those edits
    existing = [filename for filename in (args.output, args.units_output) if os.path.exists(filename)]
    if existing and not args.force:
        raise FileExistsError(f'The master model already exists ({", ".join(existing)}); use --force to overwrite')
    converter = LinkmlConverter(args.xsd, args.ome_xsd)
    schema, units = converter.convert()
    write_schema(schema, args.output)
    write_schema(units, args.units_output)
    print(f'Wrote {args.output}: {len(schema["classes"])} classes, {len(schema["enums"])} enums, '
          f'{len(schema["types"])} types; {args.units_output}: {len(units["enums"])} unit enums')
    for where, id_type in converter.unresolved_refs:
        print(f'  unresolved reference {where} ({id_type}), kept as a string')


def run_metaseed(args):
    generator = MetaseedGenerator(args.model)
    profile = generator.generate(args.name, args.version)
    write_metaseed_profile(profile, args.output)
    print(f'Wrote {args.output}: profile {profile["name"]} {profile["version"]}, {len(profile["entities"])} entities, '
          f'{sum(len(entity["fields"]) for entity in profile["entities"].values())} fields; '
          f'{len(generator.expanded)} slots over an abstract class written as one field per subtype')


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
                        help='Path to the imaging model (LinkML), or a JSON schema tree')
    convert_parser.add_argument('--mappings', default=DEFAULT_MAPPINGS_FILE,
                        help='Path to mappings.json')
    convert_parser.set_defaults(func=run_convert)

    export_parser = subparsers.add_parser(
        'export', help='Convert source metadata into metaseed datasets of the profile')
    export_parser.add_argument('--input', required=True,
                        help='Folder of source metadata files')
    export_parser.add_argument('--output', required=True,
                        help='Folder to write the datasets to')
    export_parser.add_argument('--profile', default=DEFAULT_METASEED_FILE,
                        help='Path to the metaseed profile YAML')
    export_parser.add_argument('--schema', default=DEFAULT_SCHEMA_FILE,
                        help='Path to the imaging model (LinkML), or a JSON schema tree')
    export_parser.add_argument('--mappings', default=DEFAULT_MAPPINGS_FILE,
                        help='Path to mappings.json')
    export_parser.set_defaults(func=run_export)

    linkml_parser = subparsers.add_parser(
        'linkml', help='Create the LinkML master model from the LiMi XSD')
    linkml_parser.add_argument('--xsd', default=DEFAULT_XSD_FILE,
                        help='Path to the LiMi XSD')
    linkml_parser.add_argument('--ome-xsd', default=DEFAULT_OME_XSD_FILE,
                        help='Path to the OME XSD, for descriptions the LiMi XSD leaves out')
    linkml_parser.add_argument('--output', default=DEFAULT_LINKML_FILE,
                        help='Path to write the LinkML model to')
    linkml_parser.add_argument('--units-output', default=DEFAULT_UNITS_FILE,
                        help='Path to write the LinkML units schema to')
    linkml_parser.add_argument('--force', action='store_true',
                        help='Overwrite an existing model, discarding any edits to it')
    linkml_parser.set_defaults(func=run_linkml)

    metaseed_parser = subparsers.add_parser(
        'metaseed', help='Generate a metaseed profile from the LinkML master model')
    metaseed_parser.add_argument('--model', default=DEFAULT_LINKML_FILE,
                        help='Path to the LinkML model')
    metaseed_parser.add_argument('--output', default=DEFAULT_METASEED_FILE,
                        help='Path to write the metaseed profile YAML to')
    metaseed_parser.add_argument('--name', default=None,
                        help="Profile name (default: the model's name)")
    metaseed_parser.add_argument('--version', default=None,
                        help="Profile version, in x.y format (default: from the model's version)")
    metaseed_parser.set_defaults(func=run_metaseed)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()

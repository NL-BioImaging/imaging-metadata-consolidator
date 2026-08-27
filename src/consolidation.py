from file.json_serialisation import serialise_json, deserialise_json
from file.yaml_serialisation import serialise_yaml, deserialise_yaml
import glob
from helper import create_source
import os.path

from Consolidator import Consolidator


def consolidation(schema_filename, input_filenames):
    consolidator = Consolidator()
    consolidator.import_schema(schema_filename)

    for filename in input_filenames:
        # if os.path.splitext(filename)[1].lower() in ('.json', '.yaml', '.yml'):
        #     with open(filename, 'r') as file:
        #         if filename.endswith('.json'):
        #             acquisition_metadata = deserialise_json(file.read())
        #         else:
        #             acquisition_metadata = deserialise_yaml(file.read())
        # else:
        #     source = create_source(filename)
        #     source.init_metadata()
        #     acquisition_metadata = source.get_acquisition_metadata()
        # consolidator.add_data(acquisition_metadata)
        consolidator.add_dataset(filename)

    return consolidator.dump()


def extract_acquisition_metadata(input_filenames, output_format='json'):
    for filename in input_filenames:
        source = create_source(filename)
        source.init_metadata()
        acquisition_metadata = source.get_acquisition_metadata()
        # export to json or yaml
        output_filename = os.path.splitext(filename)[0] + '.' + output_format
        with open(output_filename, 'w') as file:
            if output_format == 'json':
                file.write(serialise_json(acquisition_metadata))
            elif output_format == 'yaml':
                file.write(serialise_yaml(acquisition_metadata))


if __name__ == '__main__':
    schema_filename = 'models/fullSchema.json'
    input_filenames = glob.glob('D:/slides/tiff/acquisition_metadata/*')
    output = 'output/'

    results = consolidation(schema_filename, input_filenames)

    with open(output + 'schema.json', 'w') as file:
        file.write(serialise_json(results['schema']))
    for dataset in results['datasets']:
        with open(output + dataset['name'] + '.json', 'w') as file:
            file.write(serialise_json(dataset['metadata']))

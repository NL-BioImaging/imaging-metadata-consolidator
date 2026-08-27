from Consolidator import Consolidator
import glob
from helper import create_source


def consolidation(schema_filename, input_filenames):
    consolidator = Consolidator()
    consolidator.import_schema(schema_filename)

    for filename in input_filenames:
        source = create_source(filename)
        metadata = source.init_metadata()
        consolidator.add(source.get_name(), metadata)
    result = consolidator.consolidate()
    return result


if __name__ == '__main__':
    schema_filename = 'models/fullSchema.json'
    input_filenames = glob.glob('C:/Project/slides/tiff/*.tif*')
    consolidated = consolidation(schema_filename, input_filenames)
    #print(consolidated)

    for key, value in consolidated.items():
        print(key, value)

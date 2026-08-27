from Consolidator import Consolidator
import glob
from helper import create_source


def consolidation(input_filenames):
    consolidator = Consolidator()

    for filename in input_filenames:
        source = create_source(filename)
        metadata = source.init_metadata()
        consolidator.add(source.get_name(), metadata)
    result = consolidator.consolidate()
    return result


if __name__ == '__main__':
    input_filenames = glob.glob('C:/Project/slides/tiff/*.tif*') + glob.glob('C:/Project/slides/ome-xml/*')
    consolidated = consolidation(input_filenames)
    print(consolidated)

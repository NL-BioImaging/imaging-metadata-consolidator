import numpy as np
from ome_types.model import *
from tifffile import xml2dict

from src.color_conversion import rgba_to_int, int_to_rgba
from src.util import *


def metadata_to_dict(xml_metadata):
    metadata = xml2dict(xml_metadata)
    if 'OME' in metadata:
        metadata = metadata['OME']
    return metadata


def read_ome_xml_metadata(metadata):
    pixel_size = {}
    position = {}
    channels = []
    rows = set()
    columns = set()
    fields = set()
    wells = {}
    image_refs = {}
    acquisition_metadata = {}

    image0 = ensure_list(metadata.get('Image', []))[0]
    is_plate = 'Plate' in metadata
    if is_plate:
        for plate in ensure_list(metadata['Plate']):
            name = plate.get('Name')
            row_naming_convention = plate.get('RowNamingConvention', NamingConvention.LETTER.name)
            column_naming_convention = plate.get('ColumnNamingConvention', NamingConvention.NUMBER.name)
            for well in ensure_list(plate.get('Well', [])):
                row = create_row_col_label(well['Row'], row_naming_convention)
                column = create_row_col_label(well['Column'], column_naming_convention)
                rows.add(row)
                columns.add(column)
                label = f'{row}{column}'
                wells[label] = well['ID']
                image_refs[label] = {}
                for sample in ensure_list(well.get('WellSample', [])):
                    sample_id_parts = sample['ID'].split(':')
                    field_id = sample_id_parts[-1]
                    fields.add(int(field_id))
                    image_refs[label][field_id] = sample['ImageRef']['ID']
            if 'Rows' in plate:
                rows = [create_row_col_label(row, row_naming_convention) for row in range(plate['Rows'])]
            else:
                rows = sorted(rows)
            if 'Columns' in plate:
                columns = [create_row_col_label(col, column_naming_convention) for col in range(plate['Columns'])]
            else:
                columns = sorted(columns, key=int)
        wells = list(wells.keys())
        fields = sorted(fields)
    else:
        name = image0.get('Name')
    acquisition_datetime = image0.get('AcquisitionDate')
    pixels = image0.get('Pixels', {})
    dtype0 = pixels['Type'].lower()
    if dtype0 in ['float', 'double']:
        dtype0 = 'float64' if dtype0 == 'double' else 'float32'
    dtype = np.dtype(dtype0)
    if 'PhysicalSizeX' in pixels:
        pixel_size['x'] = convert_to_um(float(pixels.get('PhysicalSizeX')), pixels.get('PhysicalSizeXUnit'))
    if 'PhysicalSizeY' in pixels:
        pixel_size['y'] = convert_to_um(float(pixels.get('PhysicalSizeY')), pixels.get('PhysicalSizeYUnit'))
    if 'PhysicalSizeZ' in pixels:
        pixel_size['z'] = convert_to_um(float(pixels.get('PhysicalSizeZ')), pixels.get('PhysicalSizeZUnit'))
    plane = pixels.get('Plane')
    if plane:
        if 'PositionX' in plane:
            position['x'] = convert_to_um(float(plane.get('PositionX')), plane.get('PositionXUnit'))
        if 'PositionY' in plane:
            position['y'] = convert_to_um(float(plane.get('PositionY')), plane.get('PositionYUnit'))
        if 'PositionZ' in plane:
            position['z'] = convert_to_um(float(plane.get('PositionZ')), plane.get('PositionZUnit'))
    for channel0 in ensure_list(pixels.get('Channel', [])):
        channel = {}
        if 'Name' in channel0:
            channel['label'] = channel0['Name']
        if 'Color' in channel0:
            channel['color'] = int_to_rgba(channel0['Color'])
        # all additional channel metadata
        for key, value in channel0.items():
            if key not in ['Name', 'Color'] and value is not None:
                channel[camel_to_snake(key)] = value
        channels.append(channel)
    if 'SignificantBits' in pixels:
        bits_per_pixel = int(pixels['SignificantBits'])
    else:
        bits_per_pixel = dtype.itemsize * 8

    # all additional metadata
    acquisition_metadata.update(camel_to_snake_keys_dict(metadata.get('Instrument', {})))
    acquisition_metadata.update(camel_to_snake_keys_dict(image0.get('ObjectiveSettings', {})))

    for annotations_type, annotations in metadata.get('StructuredAnnotations', {}).items():
        for annotation in ensure_list(annotations):
            key, value = annotation.get('ID'), annotation.get('Value')
            if 'Namespace' in annotation:
                key = annotation['Namespace']
            if 'pyramidresolution' not in key.lower():
                if isinstance(value, dict) and 'M' in value:
                    value = {item.get('K'): item.get('value') for item in ensure_list(value['M'])}
                acquisition_metadata[key] = value

    return (name, is_plate, pixel_size, position, dtype, bits_per_pixel, channels, acquisition_metadata, acquisition_datetime,
            wells, list(rows), list(columns), list(fields), image_refs)


def get_row_col_len_type(labels):
    max_index = max(get_row_col_index(label) for label in labels)
    nlen = max_index + 1
    is_digits = [label.isdigit() for label in labels]
    if np.all(is_digits):
        naming_convention = NamingConvention.NUMBER
    else:
        naming_convention = NamingConvention.LETTER
    return nlen, naming_convention


def get_row_col_index(label):
    if label.isdigit():
        index = int(label) - 1
    else:
        index = ord(label.upper()) - ord('A')
    return index


def create_row_col_label(index, naming_convention):
    if naming_convention.lower() == NamingConvention.LETTER.name.lower():
        label = chr(ord('A') + index)
    else:
        label = index + 1
    return str(label)

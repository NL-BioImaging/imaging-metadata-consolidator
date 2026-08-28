from file.json_serialisation import serialise_json, deserialise_json
from file.yaml_serialisation import serialise_yaml, deserialise_yaml
import glob
from fnmatch import fnmatchcase
from helper import create_source
import os.path

from Consolidator import Consolidator


# Generic source metadata paths mapped to the consolidated model.  Where LiMi
# has no semantically equivalent light-microscopy field, the target model is
# extended with explicit electron-microscopy concepts instead of using a field
# that merely has a similar value type.  Identity mappings are omitted.
MAPPINGS = {
    "System.ProductName": "Instrument.Name",
    "System.SoftwareVersion": "Software.AcquisitionSoftware.Version",
    "User.UserName": "Acquisition.Operator.Name",
    "Beam.WD": "ElectronBeam.WorkingDistance.Value",
    "Beam.Focus": "ElectronBeam.Focus",
    "Beam.HFW": "Scan.FieldOfView.X.Value",
    "Beam.BeamType": "ElectronBeam.Type",
    "Beam.BeamMode": "ElectronBeam.Mode",
    "Beam.RealAbsCurrent": "ElectronBeam.Current.Value",
    "Beam.AstigX": "ElectronBeam.Stigmator.X",
    "Beam.AstigY": "ElectronBeam.Stigmator.Y",
    "Beam.ShiftX": "ElectronBeam.Shift.X",
    "Beam.ShiftY": "ElectronBeam.Shift.Y",
    "Detector.DetectorName": "Detector.Name",
    "Scan.PointTime": "Image.Plane.PixelDwellTime",
    "Scan.FrameTime": "Scan.FrameTime.Value",
    "Scan.ResolutionX": "Image.Pixels.SizeX",
    "Scan.ResolutionY": "Image.Pixels.SizeY",
    "Stage.StagePosX": "SamplePositioning.Stage.Position.X.Value",
    "Stage.StagePosY": "SamplePositioning.Stage.Position.Y.Value",
    "Stage.StagePosZ": "SamplePositioning.Stage.Position.Z.Value",
    "Stage.StagePosR": "SamplePositioning.Stage.Rotation.Value",
    "Stage.StagePosT": "SamplePositioning.Stage.Tilt.Value",
    "Make": "Instrument.Manufacturer",
    "Model": "Instrument.Model",
    "name": "Image.Name",
    "datetime": "Image.AcquisitionDate",
    "pixelsizex": "Image.Pixels.PhysicalSizeX",
    "pixelsizey": "Image.Pixels.PhysicalSizeY",
    "magnification": "Magnification.Objective.CalibratedMagnification",
    "cameraname": "Detector.Name",
    "picturetype": "Image.Type",
    "time": "Image.AcquisitionDate",
    "currentUser": "Acquisition.Operator.Name",
    "pixelWidth.value": "Image.Pixels.PhysicalSizeX",
    "pixelWidth.unit": "Image.Pixels.PhysicalSizeXUnit",
    "pixelHeight.value": "Image.Pixels.PhysicalSizeY",
    "pixelHeight.unit": "Image.Pixels.PhysicalSizeYUnit",
    "samplePosition.x": "SamplePositioning.Stage.Position.X.Value",
    "samplePosition.y": "SamplePositioning.Stage.Position.Y.Value",
    "acquisition.scan.dwellTime.value": "Image.Plane.PixelDwellTime",
    "acquisition.scan.dwellTime.unit": "Image.Plane.PixelDwellTimeUnit",
    "acquisition.scan.rotation": "Scan.Rotation.Value",
    "acquisition.scan.spotSize": "ElectronBeam.SpotSize",
    "acquisition.scan.sourceTilt.x": "ElectronBeam.SourceTilt.X",
    "acquisition.scan.sourceTilt.y": "ElectronBeam.SourceTilt.Y",
    "acquisition.scan.stigmator.x": "ElectronBeam.Stigmator.X",
    "acquisition.scan.stigmator.y": "ElectronBeam.Stigmator.Y",
    "acquisition.scan.highVoltage.value": "ElectronBeam.AccelerationVoltage.Value",
    "acquisition.scan.highVoltage.unit": "ElectronBeam.AccelerationVoltage.Unit",
    "acquisition.scan.emissionCurrent.value": "ElectronBeam.EmissionCurrent.Value",
    "acquisition.scan.emissionCurrent.unit": "ElectronBeam.EmissionCurrent.Unit",
    "workingDistance.value": "ElectronBeam.WorkingDistance.Value",
    "workingDistance.unit": "ElectronBeam.WorkingDistance.Unit",
    "instrument.softwareVersion": "Software.AcquisitionSoftware.Version",
    "instrument.uniqueID": "Instrument.ID",
    "instrument.edition": "Instrument.Model",
    "instrument.type": "Instrument.Type",
    "Instrument.InstrumentId": "Instrument.ID",
    "Instrument.InstrumentModel": "Instrument.Model",
    "Instrument.InstrumentClass": "Instrument.Type",
    "Instrument.ControlSoftwareVersion": "Software.AcquisitionSoftware.Version",
    "Acquisition.AcquisitionStartDatetime.DateTime": "Image.AcquisitionDate",
    "Acquisition.AcquisitionDatetime.DateTime": "Image.AcquisitionDate",
    "Acquisition.BeamType": "ElectronBeam.Type",
    "Acquisition.SourceType": "ElectronSource.Type",
    "Optics.AccelerationVoltage": "ElectronBeam.AccelerationVoltage.Value",
	"Optics.CameraLength": "ElectronOptics.CameraLength.Value",
    "Optics.SpotIndex": "ElectronBeam.SpotIndex",
    "Optics.BeamConvergence": "ElectronBeam.ConvergenceAngle.Value",
    "Optics.Defocus": "ElectronBeam.Defocus.Value",
    "Optics.StemFocus": "ElectronBeam.Focus",
    "Optics.OperatingMode": "ElectronOptics.OperatingMode",
    "Optics.TemOperatingSubMode": "ElectronOptics.OperatingSubMode",
    "Optics.ProjectorMode": "ElectronOptics.ProjectorMode",
    "Stage.Position.x": "SamplePositioning.Stage.Position.X.Value",
    "Stage.Position.y": "SamplePositioning.Stage.Position.Y.Value",
    "Stage.Position.z": "SamplePositioning.Stage.Position.Z.Value",
    "Stage.AlphaTilt": "SamplePositioning.Stage.Tilt.Alpha.Value",
    "Stage.BetaTilt": "SamplePositioning.Stage.Tilt.Beta.Value",
    "Stage.HolderType": "SamplePreparation.SampleHolder.Type",
    "Scan.DwellTime": "Image.Plane.PixelDwellTime",
    "Scan.ScanSize.width": "Image.Pixels.SizeX",
    "Scan.ScanSize.height": "Image.Pixels.SizeY",
    "Scan.ScanRotation": "Scan.Rotation.Value",
    "Scan.LineTime": "Scan.LineTime.Value",
    "BinaryResult.PixelSize.width": "Image.Pixels.PhysicalSizeX",
    "BinaryResult.PixelSize.height": "Image.Pixels.PhysicalSizeY",
    "BinaryResult.PixelUnitX": "Image.Pixels.PhysicalSizeXUnit",
    "BinaryResult.PixelUnitY": "Image.Pixels.PhysicalSizeYUnit",
    "Application.Version": "Software.AcquisitionSoftware.Version",
    "applicationID": "Software",
    "version": "Software",
    "databarHeight": "Image",
    "databarFields": "Image",
    "databarLabel": "Image",
    "displayWidth": "Image",
    "appliedContrast": "Image.Corrections",
    "appliedBrightness": "Image.Corrections",
    "appliedGamma": "Image.Corrections",
    "displayBlackLevel": "Image.Corrections",
    "displayWhiteLevel": "Image.Corrections",
    "integrations": "Scan.LineIntegrationCount",
    "samplePressureEstimate": "Instrument.Vacuum",
    "Sample": "SamplePreparation.Sample",
    "Image.Width": "Image.Pixels.SizeX",
    "Image.Height": "Image.Pixels.SizeY",
    "Scan.FOV_X.value": "Scan.FieldOfView.X.Value",
    "Scan.FOV_X.units": "Scan.FieldOfView.X.Unit",
    "Scan.FOV_Y.value": "Scan.FieldOfView.Y.Value",
    "Scan.FOV_Y.units": "Scan.FieldOfView.Y.Unit",
    "Scan.ScanRot.value": "Scan.Rotation.Value",
    "Scan.ScanRot.units": "Scan.Rotation.Unit",
    "Scan.Focus": "ElectronBeam.Focus",
    "Scan.StigX": "ElectronBeam.Stigmator.X",
    "Scan.StigY": "ElectronBeam.Stigmator.Y",
    "Stage.X.value": "SamplePositioning.Stage.Position.X.Value",
    "Stage.X.units": "SamplePositioning.Stage.Position.X.Unit",
    "Stage.Y.value": "SamplePositioning.Stage.Position.Y.Value",
    "Stage.Y.units": "SamplePositioning.Stage.Position.Y.Unit",
    "Stage.Z.value": "SamplePositioning.Stage.Position.Z.Value",
    "Stage.Z.units": "SamplePositioning.Stage.Position.Z.Unit",
    "Stage.Tilt.value": "SamplePositioning.Stage.Tilt.Value",
    "Stage.Tilt.units": "SamplePositioning.Stage.Tilt.Unit",
    "Stage.Rot.value": "SamplePositioning.Stage.Rotation.Value",
    "Stage.Rot.units": "SamplePositioning.Stage.Rotation.Unit",

    # Generalized subtree rules. Exact entries above take precedence. These
    # rules cover numbered components (Detector-0, Aperture-1), generated
    # operation UUIDs, and vendor-specific fields without encoding instance
    # identifiers in the consolidated schema.
    "Beam.*": "ElectronBeam",
    "HV.*": "ElectronBeam.HighVoltage",
    "User.*": "Acquisition.Operator",
    "Detector.*": "Detector",
    "System.*": "Instrument",
    "Stage.*": "SamplePositioning.Stage",
    "RawStage.*": "SamplePositioning.Stage.RawPosition",
    "StageBias.*": "SamplePositioning.Stage.Bias",
    "acquisition.scan.detectors.*": "Detector.Configuration",
    "acquisition.scan.*": "Scan",
    "instrument.sampleHolder.*": "SamplePreparation.SampleHolder",
    "instrument.*": "Instrument",
    "cropHint.*": "Image.CropHint",
    "multiStage.*": "SamplePositioning.Stage.MultiStage",
    "PPI.*": "Software",
    "Optics.Apertures.*": "ElectronOptics.Apertures",
    "Optics.*": "ElectronOptics",
    "Detectors.*": "Detector.Configuration",
    "DetectorMetadata.*": "Detector.Configuration",
    "BinaryResult.*": "Image.BinaryResult",
    "CustomProperties.*": "CustomProperties",
    "Operations.*": "Operations",
    "Features.*": "Features",
    "Core.*": "Instrument",
    "Sample.*": "SamplePreparation.Sample",
    "Scan.*": "Scan",
    "Vacuum.*": "Instrument.Vacuum",
    "Application.*": "Software",
    "Image.BoundingBox.*": "Image.CropHint",
    "ImageCorrections.*": "Image.Corrections",
    "Image.*": "Image"
}


def resolve_mapping(source_path):
    """Resolve an exact, repeated-metadata, or wildcard source path."""
    target = MAPPINGS.get(source_path)
    if target is not None:
        return target

    # TALOS processing operations can embed a second copy of acquisition
    # metadata below a generated operation UUID. Reuse the canonical mapping
    # for that suffix rather than creating another schema hierarchy.
    metadata_marker = '.metadata.'
    if metadata_marker in source_path:
        embedded_path = source_path.split(metadata_marker, 1)[1]
        target = resolve_mapping(embedded_path)
        if target is not None:
            return target

    for pattern, target in MAPPINGS.items():
        if '*' in pattern and fnmatchcase(source_path, pattern):
            return target
    return None


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

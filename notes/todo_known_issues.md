# Known issues and TODO

## Known issues

### Hub state

The Hub account the metaseed token acts as (j.j.m.defolter@amsterdamumc.nl) holds one draft, `imaging`
0.1, pushed by the user from `models/imaging.metaseed.yaml` (2026-09-28; valid, no problems, no
warnings); the old `LiMi-extended` draft is gone. Datasets can only be created against a published
profile, so exports are not validated on the Hub until it is published. After a change to the master
model, regenerate (`python src/main.py metaseed`) and push the profile again.

### LiMi XSD slips (worked around in the converter, original names kept)

- OpticalAperture uses `LensID` as its ID type; FilterCubeRef extends FilterCubeRef with a generic LSID;
  StageInsertRef/LightSensorRef name their ID attribute StageInsertID/LightSensorID.
- BeamSplitter has both an attribute and an element `TransmittanceProfileFile` (element slot ->
  `TransmittanceProfileFileElement`); MaskingPlate has an attribute named `ApertureNr.` (slot `ApertureNr`,
  `xsd_name` annotation) - a dot would split the slot's path.
- Typo `lluminationPowerSettingsUnit` (LightSourceSettings) kept; 7 unit slots have no value slot of their
  name (ReadNoiseUnit, XYZResolutionUnit, WavelengthUnit, MinTemperatureUnit, DevianceAngleUnit,
  ObservedIlluminationPowerAtBackObjectiveUnit, lluminationPowerSettingsUnit).
- LightSensor is referenced (LightSensorRef) but no element contains it: the only class the generated
  profile cannot reach; its references stay plain strings.
- LightPath has no Tier in the XSD; Tier 1 taken from fullSchema.json (hand edit, `Tier_source`).

### Dates and IDs are taken gracefully (user, 2026-09-28)

- Image.AcquisitionDate is a datetime (OME's xsd:dateTime; LiMi's xsd:date kept as `xsd_range`). ISO 8601
  variations are taken as they come, without conversion (T or space, with or without a zone, `Z`); a value
  that is no datetime (TALOS's "0") stays a Property. Other formats could be converted by a rule, as
  combinations.json does. metaseed accepts "2025-05-28 10:54:00" (EMSIS dataset validated locally).
- IDs and references accept any string: the 29 LSID-based ID types keep the XSD's pattern as an advisory
  `xsd_pattern` annotation only, so vendor IDs (`SS1735`, `9953543`) fit Instrument.ID. The UUID type keeps
  its pattern (a file link, no object ID).

### Generated metaseed profile

metaseed has no inheritance and no "one of": a slot over an abstract class is one field per concrete
subtype (Instrument.Laser, Instrument.Arc, ...), none required, so "an instrument has a light source" is
not enforced there. An optional ID identifier is added where metaseed would otherwise take an optional
free-text first field (MapEntry, BinData, Rights, ...).

### Per-channel mounting medium index

`ome-tiff` reports `RefrIndexMedium` per channel; channel 0's value goes to MountingMedium.RefractiveIndex,
channel 1's collides and stays in its channel item (recorded in the SourceMap). Accepted asymmetry.

### DICOM source holds dummy patient details

`sources/dicom.json` has patient fields (PatientName, PatientID, PatientBirthDate, InstitutionName,
...), which reach `output/` and, as Property records, `export/`. They are dummy values, not real
identifiers (user, 2026-09-25), so they can be committed and shared. A real DICOM source would need
de-identifying before it is added.

### Local metaseed CLI

Not installed in biomero-converter-env; a scratch venv (`pip install metaseed`, 0.54.0) works. It writes
to `%LOCALAPPDATA%/metaseed`, whatever `HOME` is set to: point `LOCALAPPDATA` and `APPDATA` at a scratch
folder. `metaseed spec import <draft> models/imaging.metaseed.yaml` then `metaseed spec validate <draft>`:
valid, no problems, no warnings (2026-09-28).

### Environment

linkml 1.11.1 in biomero-converter-env; chardet kept at 5.2.0 (linkml's ShEx generator pyshexc wants
>=7.4.1 but is unused; requests warns on 7.x).

## In progress

Master model and pipeline done (branch `metaseed-profile`, 2026-09-28).
Nothing open.

## The model and the pipeline

- Master model: `models/imaging.yaml` (LinkML, style of the OME LinkML schema
  https://github.com/gouttegd/yamf-playground/blob/main/linkml/ome/ome.yaml, LiMi's PascalCase names),
  importing `imaging_units.yaml` (units enums), `imaging_provenance.yaml` (Property, SourceFile,
  SourceMapping) and `imaging_extension.yaml` (what the source files hold beyond LiMi, mostly EM,
  formerly mappings/schema.extended.json; mixins OMEExtension, InstrumentExtension, ... used by the model's
  classes, shared Quantity {Value, Unit}, Vector2D, StagePosition). Edited by hand; version 0.1.0, id
  https://github.com/NL-BioImaging/imaging-metadata-consolidator/models/imaging.
- Created once from the whole LiMi XSD by `python src/main.py linkml` (src/LinkmlConverter.py; refuses to
  overwrite without --force). Rules: extension base -> `is_a`; an abstract `*Group` -> a slot over its
  (abstract) type with a type designator; `*Ref` -> a reference slot without `Ref` (`inlined: false`);
  Settings' ID refers to the component; the XSD's `Split` -> a `Role` field on LightSource, limited per
  class; descriptions the XSD lacks from OME 2016-06 ome.xsd (`models/ome-2016-06.xsd`, CC BY 3.0,
  attributed) or derived, each with `description_source`. The converter stays for comparing a future
  LiMi XSD; a test checks everything it yields is still in the master.
- Hand edits so far: the three imports and their mixins/CustomProperties/SourceFile slots; OME.ID/Name
  (metaseed datasets identify their root); LightPath Tier; MaskingPlate.ApertureNr; Image.AcquisitionDate
  as datetime; ID patterns advisory (see Known issues); `default_subtype`
  annotations on abstract classes (LiMi's Generic* subtypes; Stage -> MechanicalStage and Software ->
  AcquisitionSoftware chosen by the user) - where values for an abstract class go.
- Model paths (src/ModelPaths.py): start at a class with an identifier (OME, Image, Pixels, Laser, ...) and
  run through components without one: `OME.ElectronBeam.WorkingDistance.Value`,
  `Image.ObjectiveSettings.Medium`, `MechanicalStage.Position.X.Value`. mappings.json targets are these
  paths (tested); the mapper's name matching indexes them, plus aliases for abstract classes
  (`Detector.Name` -> `GenericDetector.Name`).
- metaseed profile: `python src/main.py metaseed` -> `models/imaging.metaseed.yaml` (src/MetaseedGenerator.py,
  profile `imaging`), inherited fields written out, references as ID strings, constraints from enums,
  patterns and bounds. The exporter places a record by name only at a class a model path starts at (or an
  abstract class, into its default subtype), never at a component.
- Kept as references, read by nothing: models/LiMi_XMLSchema.xsd, models/fullSchema.json (a test checks
  every property is in the model), models/LiMi_Model.json, mappings/schema.json.
- Retired (in git history): mappings/schema.extended.json, src/ProfileConverter.py (ProfileConverter,
  ProfileExtender, `profile` command), models/fullSchema.yaml, models/schema.extended.yaml.

## How new, unmapped metadata is kept

Nothing a source holds is dropped; unmapped metadata stays reachable at its source path.

In `output/` (mapper, `convert`), for example with a source
`{Make: Acme, NewVendorKey: 42, Beam: {WD: 0.005, NewBeamSetting: 'on'}, Odd: {Deep: {Value: 1.5}},
ACME_TAG: {Model: X1-rev2, Serial: S123}}`:
- `NewVendorKey` (no rule, no model name match) stays at `NewVendorKey`.
- `Beam.NewBeamSetting` lands at `OME.ElectronBeam.NewBeamSetting`: a subtree rule (`Beam.*` ->
  `OME.ElectronBeam`) carries new fields of that group along.
- `Odd.Deep.Value` (unknown group) stays as it is.
- `ACME_TAG` is a vendor wrapper: its unmapped `Serial` stays at `ACME_TAG.Serial`; its `Model` has a
  rule and goes to `Instrument.Model`, as if the wrapper were absent (had a top-level `Model` taken
  `Instrument.Model` first, it would stay at `ACME_TAG.Model` instead of overwriting).
- Every leaf gets a SourceMap entry (output path -> source path), e.g.
  `OME.ElectronBeam.NewBeamSetting: Beam.NewBeamSetting`.

In `export/` (metaseed dataset, `export`): metaseed rejects undeclared keys, so each such value is a
`Property` record under `CustomProperties` of the nearest anchor (Image, Instrument, else OME): `Name` =
source path, `Value` = JSON-encoded value, `SchemaPath` = where a rule moved it. A record that fits no
declared field (a vendor object where the model has a string) is taken apart into one Property per leaf.
Values that fit a declared field are typed, with a `SourceMapping` record (e.g. `Make` ->
`Instrument[0].Manufacturer`).

What follows from a new source or new metadata:
- The output/ and export/ freshness tests fail until `convert` and `export` are rerun; the no-data-loss
  tests confirm every new value is kept.
- `AcquisitionMetadataMapper.unmatched_fields()` lists output paths the model does not have - the
  candidates for new rules.
- To make a value typed: add a rule to mappings.json (its target a model path; add the field to
  models/imaging_extension.yaml if missing), rerun `metaseed`, `convert` and `export`; the value moves
  from a Property to a typed field.

## TODO

- [ ] Map LiMi's per-property tier (1/2/3, the `Tier` annotations) to metaseed's advisory `tier`
      (required / recommended / optional), so real vendor files are not failed on tier-3 fields.
- [ ] Unit normalisation (e.g. vendor "um" -> OME "µm") so unit fields can be typed; the
      original spelling must stay recoverable.
- [ ] Per-channel mapping (e.g. Huygens ChannelData[i] LambdaEx/LambdaEm -> each Channel's
      Fluorophore wavelengths): rules resolve from the root, so each channel's value collides.
- [ ] ObjectiveSettings.Medium/RefractiveIndex (extension) duplicate LiMi's ImmersionLiquid; decide
      whether the flat ome-tiff `medium`/`refractive_index` rules should target ImmersionLiquid instead.
- [ ] Light-source role: rules for Transmitted/Fluorescence light sources should set `Role`.
- [ ] EM groups hang under OME (as schema.extended.json had them); ElectronBeam/Optics/Source are
      instrument components or settings, Scan/Acquisition acquisition settings - move when the mapper
      paths can follow. Acquisition.Operator might be LiMi's Experimenter.
- [ ] `exact_mappings`/`close_mappings` to the OME LinkML schema, keeping importing/extending it open.
- [ ] Consider adding `DNAcropSmall.ome.json` (full OME + Huygens) as a source: a real test
      that mapped annotation values agree with the image's own OME values.
- [x] PR for `metaseed-profile`: https://github.com/NL-BioImaging/imaging-metadata-consolidator/pull/2

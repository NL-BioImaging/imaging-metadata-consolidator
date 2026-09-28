# Known issues and TODO

## Known issues

### Hub state

Published on the Hub (account j.j.m.defolter@amsterdamumc.nl): profile `imaging` 0.1, 0.2 and 1.0 (1.0 =
`models/imaging.metaseed.yaml`, model 1.0.0, 2026-09-28; valid, no problems, no warnings); the account holds
no datasets. After a change to the master model: regenerate (`python src/main.py metaseed`), run metaseed's
compatibility check against the last published version (see "Profile versions"), bump the version, and push
and publish again.

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

### Validation of the exports (2026-09-28)

All 13 export/ datasets validated with the local metaseed 0.54.0 against `imaging` 0.1 (the two TALOS
exports with their Property records sampled to 25 per anchor; the full run is ~3.5 s a record, so about
5 hours for both): 695 errors, all "Field 'X' is required" - no type, format, constraint or unknown-field
error. Most are LiMi's own requirements the sources do not state (GenericDetector 121: Manufacturer, Model,
CatalogNumber, QuantumEfficiency, ...; Pixels 108: DimensionOrder, SizeZ/C/T, PixelType; Image 104: ID, Name,
Instrument, Experiment, Sample, AcquisitionSoftware references; Objective 71; MechanicalStage 60). With the
LiMi tiers (profile 0.2) 543 of them remain, all tier 1 (EMSIS 47 -> 35, SVS 37 -> 32, platy 34 -> 32,
Delmic 12). SVS's one Property without a Name is its source key "", kept as it is. The Hub validates the
same way: a Delmic test dataset gave the same 12 issues there (deleted again, soft; the user chose local
validation only). Hub datasets need metaseed's tree serialization, not the nested export (save_dataset
silently stored an empty dataset): `MetaseedClient(...)._facade.load_nested(document)` then
`serialize(format='tree')`.

### Profile versions (2026-09-28)

`imaging` 0.1, 0.2 and 1.0 are published on the Hub. 1.0 against
0.2: 16 breaking changes, all intended (required bump major) - the EM groups moved from OME into Instrument
and Image, ObjectiveSettings.Medium/RefractiveIndex removed, the UUID fields strings with a pattern, and
ElectronSource.ID required (an identifier, as all LiMi hardware IDs). 0.2 adds the LiMi tiers: every field gets the higher LiMi
tier of the field and its class (1 required, 2 recommended, 3 and MechanicalCalibration's 4 optional), and
the XSD's `required` holds only at tier 1; untiered fields (extension, provenance) keep theirs. metaseed's
compatibility check (`metaseed.specs.compare.compare_specs(old, new)`, the check behind the Hub's "Breaking
changes"): 0.1 -> 0.2 has no breaking change (required bump minor).
A first 0.2 re-keyed StageLabel (an added ID) and MicroscopeTableSettings (a reference declared as
identifier); the generator now keeps metaseed's inferred identifier - the first field that is no
reference - and declares it where a tier made it optional. Run the check before publishing a new version.

### Generated metaseed profile

metaseed has no inheritance and no "one of": a slot over an abstract class is one field per concrete
subtype (Instrument.Laser, Instrument.Arc, ...), none required, so "an instrument has a light source" is
not enforced there. metaseed keys an entity by its `is_identifier` field, else by its first field that is
no reference; where that field is optional free text, an optional ID identifier is added (MapEntry,
BinData, Rights, ...), unless it is required in the model and optional only through its tier
(StageLabel.Name): then it is declared the identifier, so the entity keeps its key.

### Per-channel mounting medium index

`ome-tiff` reports `RefrIndexMedium` per channel; channel 0's value goes to MountingMedium.RefractiveIndex,
channel 1's collides and stays in its channel item (recorded in the SourceMap). Accepted asymmetry.

### DICOM source holds dummy patient details

`sources/dicom.json` has patient fields (PatientName, PatientID, PatientBirthDate, InstitutionName,
...), which reach `output/` and, as Property records, `export/`. They are dummy values, not real
identifiers (user, 2026-09-25), so they can be committed and shared. A real DICOM source would need
de-identifying before it is added.

### Validating datasets with metaseed is slow - worked around (2026-09-28)

`metaseed validate` took ~3.5-10 s a record (TALOS ~3,000 records: hours). Profiled: almost all the time is
metaseed re-reading and re-parsing the 1.2 MB profile YAML (pure-Python yaml, ~4 s each) - a new SpecLoader,
with an empty `_profile_cache`, for every nested entity it validates (49 loads for EMSIS). Sharing one cache
across loaders (patch `metaseed.specs.loader.SpecLoader.__init__` to set `self._profile_cache` to one dict,
then run `metaseed.cli.app.app` as `metaseed validate ...`) gives identical results in seconds: all 13 full
exports against 1.0 in 36 s. Validation against 1.0 (full, no sampling): Delmic 12, EMSIS 35, SVS 32, platy
32, DICOM 30, Zeiss 31, Cikteq 40, Phenom 54, ome-tiff 57, Leica 29, Leica tilescan 97, TALOS 56, TALOS 2 56
errors - all "Field 'X' is required", no other error, no crash. Worth reporting to metaseed.

### Local metaseed CLI

Not installed in biomero-converter-env; a scratch venv (`pip install metaseed`, 0.54.0) works. It writes
to `%LOCALAPPDATA%/metaseed`, whatever `HOME` is set to: point `LOCALAPPDATA` and `APPDATA` at a scratch
folder. `metaseed spec import <draft> models/imaging.metaseed.yaml` then `metaseed spec validate <draft>`:
valid, no problems, no warnings (2026-09-28).

### Environment

linkml 1.11.1 in biomero-converter-env; chardet kept at 5.2.0 (linkml's ShEx generator pyshexc wants
>=7.4.1 but is unused; requests warns on 7.x).

## In progress

Current task (user, 2026-09-28): work through all TODOs, one commit each. Previous task (sources keeping
their top levels) committed 35475fb; its metaseed validation against 0.2: Zeiss 31 and Phenom 53 errors,
all required fields; ome-tiff crashed metaseed - OME.UUID is `uri` with a pattern, and metaseed applies the
pattern to the parsed URL (pydantic "Input should be a valid string").
Decided (user): immersion values go to ImmersionLiquid, the extension's ObjectiveSettings.Medium/
RefractiveIndex are removed; Role deferred until a source has light sources; EM groups option B - LiMi's
hardware/settings split: ElectronSource under Instrument, ElectronBeamSettings (referring to the
ElectronSource), ElectronOpticsSettings, ScanSettings under Image, Acquisition.Operator -> Experimenter,
Acquisition.StartDate -> Image.AcquisitionDate. Removing/moving fields is breaking: next version 1.0.0.
Plan, one commit each:
1. generator: a `uri` field with a pattern -> `string` with the pattern
2. immersion -> ImmersionLiquid, extension fields removed
3. EM groups option B
4. per-channel mapping (Huygens ChannelData[i] -> Channel[i])
5. unit normalisation (vendor "um" -> "µm", original kept)
6. exact_mappings/close_mappings to the OME LinkML schema
7. Role TODO reworded (deferred)
8. release 1.0.0: regenerate, compatibility check (breaking expected), validate, write-up
Progress: 1-8 done, 8 = release 1.0.0 (exports validated against 1.0, see "Validating datasets with metaseed is slow"); (7: Role TODO reworded, deferred; 6: exact_mappings/close_mappings with prefix ome: (https://schemas.incenp.org/ome/v1/core/) on 21 classes and 55 fields, by name and by hand; name matches with another meaning as close (the extension's Detector Type/Gain/Offset hold per-image vendor values, OME's are detector specs); no copy of ome.yaml in the repo (no licence stated), a test checks the prefixes; importing/extending ome.yaml stays open; 5: 338 unit aliases in imaging_units.yaml - LiMi's unit names and an ASCII form (um, uA, C for °C; no bare A for Å) - and the exporter stores an alias as the unit, SourceMapping.SourceValue keeping the source's spelling; Phenom 41 -> 43 typed; 4: rule targets may hold [*], the index of the list item the value comes from; Huygens LambdaEx/Em and an OME document's channel wavelengths -> Pixels.Channel[*].Fluorophore; the whole-list rule Image.Pixels.Channel -> Channel removed, the exporter places an OME document's channels structurally; ome-tiff 39 -> 47 typed; 3: 61 rules retargeted; TALOS's AcquisitionStartDatetime "1683922216" is a Unix timestamp, no datetime, and stays a Property; 2: OME's Medium "Oil" fits no ImmersionLiquidType - LiMi has Mineral/Silicone Oil - and stays a Property; Huygens' RefrIndexLensMedium now meets OME's value, equal, and stays a Property).

## The model and the pipeline

- Master model: `models/imaging.yaml` (LinkML, style of the OME LinkML schema
  https://github.com/gouttegd/yamf-playground/blob/main/linkml/ome/ome.yaml, LiMi's PascalCase names),
  importing `imaging_units.yaml` (units enums), `imaging_provenance.yaml` (Property, SourceFile,
  SourceMapping) and `imaging_extension.yaml` (what the source files hold beyond LiMi, mostly EM,
  formerly mappings/schema.extended.json; mixins OMEExtension, InstrumentExtension, ... used by the model's
  classes, shared Quantity {Value, Unit}, Vector2D, StagePosition). Edited by hand; version 0.2.0, id
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
  run through components without one: `Image.ElectronBeamSettings.WorkingDistance.Value`,
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
- `Beam.NewBeamSetting` lands at `Image.ElectronBeamSettings.NewBeamSetting`: a subtree rule (`Beam.*` ->
  `Image.ElectronBeamSettings`) carries new fields of that group along.
- `Odd.Deep.Value` (unknown group) stays as it is.
- `ACME_TAG` is a vendor wrapper: its unmapped `Serial` stays at `ACME_TAG.Serial`; its `Model` has a
  rule and goes to `Instrument.Model`, as if the wrapper were absent (had a top-level `Model` taken
  `Instrument.Model` first, it would stay at `ACME_TAG.Model` instead of overwriting).
- Every leaf gets a SourceMap entry (output path -> source path), e.g.
  `Image.ElectronBeamSettings.NewBeamSetting: Beam.NewBeamSetting`.

In `export/` (metaseed dataset, `export`): metaseed rejects undeclared keys, so each such value is a
`Property` record under `CustomProperties` of the nearest anchor (Image, Instrument, else OME): `Name` =
source path, `Value` = JSON-encoded value, `SchemaPath` = where a rule moved it. A record that fits no
declared field (a vendor object where the model has a string) is taken apart into one Property per leaf.
Values that fit a declared field are typed, with a `SourceMapping` record (e.g. `Make` ->
`Instrument[0].Manufacturer`). Record IDs follow OME's `Type:N` convention (`Property:2653`,
`SourceMapping:12`, `SourceFile:0`); what a record is about is in `Name`/`SchemaPath`/`Field` - IDs made
of paths were considered and not taken (user, 2026-09-28).

What follows from a new source or new metadata:
- The output/ and export/ freshness tests (tests/test_convert.py, tests/test_dataset_exporter.py) fail
  until `convert` and `export` are rerun; the no-data-loss tests (tests/test_no_data_loss.py) confirm
  every new value is kept.
- `AcquisitionMetadataMapper.unmatched_fields()` lists output paths the model does not have - the
  candidates for new rules.
- To make a value typed: add a rule to mappings.json (its target a model path - a test checks it is in
  the model; add the field to models/imaging_extension.yaml if missing). A change to the model makes the
  committed profile out of date (a test fails until `python src/main.py metaseed` is rerun); then rerun
  `convert` and `export`, and the value moves from a Property to a typed field. To publish the changed
  profile, see "Hub state".

## TODO

- [ ] Light-source role, when a source holds light sources (none does yet, so rules setting it would have
      nothing to act on or be tested with; user, 2026-09-28): rules for Transmitted/Fluorescence light
      sources should set `LightSource.Role`.

# Known issues and TODO

## Known issues

### Hub draft behind the repo profile

The Hub draft `LiMi-596b481a` was imported before the Property/SourceFile entities (a59807f).
Re-import `models/fullSchema.yaml` on the Hub's Import page to bring it up to date.

### Unused shared entities in the profile

9 entities are unreachable from the `OME` root: `IlluminationWavelengthRange`, `LEDModule`,
`WavelengthRange`, `TransmittanceRange`, `ReflectanceRange`, `ReflectionWavelengthRangeSettings`,
`TransmissionWavelengthRangeSettings`, `WavelengthProfileFile`, `Pump`. The JSON gives each parent
its own inline copy instead (e.g. `Arc_IlluminationWavelengthRange`), and `Laser.Pump` points to
`Laser`. Kept, not deleted; `tests/test_profile_converter.py` pins this set.

### Links to entities fullSchema.json never defines

22 fields link to `Filter`, `Lens`, `MirroringDevice`, `Aperture` (5 each), `Experimenter`,
`LightSensor`, which have no schema of their own; they stay plain `string` fields.

### Per-channel mounting medium index

`ome-tiff` reports `RefrIndexMedium` per channel; channel 0's value goes to the top-level
`SamplePreparation.MountingMedium.RefractiveIndex`, channel 1's collides and stays in its channel
item (recorded in the SourceMap). Accepted asymmetry.

### Local metaseed CLI writes to AppData

`metaseed spec save` writes to `%LOCALAPPDATA%/metaseed/specs`, whatever `HOME` is set to. Point
`LOCALAPPDATA` (and `APPDATA`) at a scratch folder when trying profiles locally.

## In progress

Export: mapper output -> a metaseed dataset of the LiMi profile (`OME` root), so real source files
can be validated with `validate_dataset` / `metaseed validate`, without losing any source value or
key name.

Done so far (branch `metaseed-profile`, pushed to origin up to c04ce0c; no PR yet):
- 5385662 profile converter (`python src/main.py profile`): `fullSchema.json` + containment from
  `LiMi_XMLSchema.xsd` -> `models/fullSchema.yaml`, `OME` root; valid in metaseed (local and Hub).
- a914b1f every converted file carries a `SourceMap` {output path: source path}; collapsed keys
  kept as `id`/`SourceKey`; no overwrites (fall back to the source path, or fail loudly); empty
  containers kept. `tests/test_no_data_loss.py` checks every source leaf, value and type, at the
  output path its SourceMap entry names, in memory and after a YAML round trip.
- 938fcf5 mappings.json rules resolve from the document root inside list items (the Annotation
  rules put Software versions and the medium index inside `Annotation[0]` before).
- a59807f profile gains `Property` (ID, Name = source path, Value = JSON-encoded, Unit, Source =
  SourceFile ID) as `CustomProperties` on `OME`, `Image`, `Instrument`, and `SourceFile` (ID, Name,
  SHA-256 Checksum, Format) as a list on `Image`.

Findings for the export:
- Dataset format: the root entity as a nested YAML/JSON document, children inline (dicts and
  lists). `metaseed validate <file> -p limi -v 2.1 -e OME` reports missing required fields and
  rejects any undeclared key ("Extra inputs are not permitted").
- Mapper output is `category -> entity -> field` (`schema.extended.json`): an entity instance is
  wherever an entity name holds a dict (`Detector.Channel` is an integer, not the entity).
  Placement must follow the profile tree, not the categories: `Image.Plane`/`Image.Channel` go
  under `Pixels`; take the shortest path from `OME`.
- Category-level fields (`Instrument.Manufacturer`, `Detector.Gain`, ...) and all EM groups have
  no profile field -> `Property` records.
- Real data will fail many required fields (the JSON marks e.g. Manufacturer/CatalogNumber
  required everywhere) - see the tier TODO.

Plan:
1. Rule: a value goes into a typed field only if it fits exactly (type, constraints, free slot);
   otherwise a `Property` with its source path (from the SourceMap) and JSON-encoded value, under
   the nearest anchor (`Image`, `Instrument`, else `OME`).
2. One `SourceFile` per converted file (name, SHA-256).
3. Extend the no-data-loss test to the export: every source leaf recoverable from the dataset.
4. Validate the exported sources with the local CLI, then on the Hub.

Progress (not committed yet):
- 1-3 done: `src/DatasetExporter.py`, `python src/main.py export --input sources --output <dir>`;
  profile gains `SourceMapping` and `Property.SchemaPath` (146 entities, valid in metaseed).
- `tests/test_dataset_exporter.py` (placement, fits, anchors, collisions, only declared keys on all
  sources) and `DatasetNoDataLossTest` in `tests/test_no_data_loss.py` (every source path's value
  or key recovered from the dataset's SourceMappings + Properties, in memory and from the written
  YAML). Mutation-checked: a dropped Property, a dropped mapping and a changed value are each
  reported. 48 tests pass.
- Most values are Properties for now, e.g. TFS TALOSF: 6 typed mappings, 1950 Properties (EM
  metadata has no profile fields yet - see the extension TODO). Vendor units like "um" don't fit
  OME's unit enums ("µm") and stay Properties.
- eea2c52 export committed. Tier made optional (profile regenerated, valid; not committed yet).
- 4 local `metaseed validate` of the 8 datasets (profile at c04ce0c): 6 finished, 155 errors, all
  "Field 'X' is required" - no unknown keys, no type or constraint errors. The two TALOS datasets
  (1950 / 3008 Properties) did not finish within 10 min; validation takes ~2-3s a record locally
  (Delmic 2 records 17s, Cikteq 81 records 209s, ome-tiff 134 records 333s). An earlier run only
  seemed to hang because the laptop was offline/asleep.
- Missing required fields are LiMi's own requirements the sources don't state (Image.Name/ID,
  Pixels.DimensionOrder/SizeZ/C/T/PixelType, Objective.Manufacturer/Model/CatalogNumber,
  AcquisitionSoftware.Developer/WebsiteURL, Experiment.Purpose, Sample.Organism, ...).
- Next: validate on the Hub (validate_dataset) once the Hub draft is re-imported. Required fields
  in the destination model are ignored for now (user).
- ome-tiff reached few typed fields because `sources/ome-tiff.json` is mostly one Huygens SVI
  annotation (124 of 128 Properties) with Huygens names, which no name match can place. (Name
  matching compares the whole source path to schema path ends; no `Metadata.`-style wrapper
  exists in real files, so no tail matching needed.) Added 5 Huygens rules, validated against
  `napari-meta-tiff/output/DNAcropSmall.ome.json` (same image, its own OME Pixels + the same
  annotation): DeltaX/Y/Z = PhysicalSizeX/Y/Z (µm), DeltaT = TimeIncrement (s),
  RefrIndexLensMedium = OME ObjectiveSettings.RefractiveIndex (immersion, 1.518) ->
  LiMi ObjectiveSettings.ImmersionLiquid.RefractiveIndex. ome-tiff typed values 6 -> 11.
  Not added: LambdaEx/LambdaEm (per channel; OME stores 424/461 where Huygens has
  424.119995/461.0).

Decided (user): values placed in typed fields keep their source key through `SourceMapping`
records (ID, Field = dataset path, Source = source path), listed as `Mapping` on each
`SourceFile` - the metaseed form of the SourceMap. Each value is stored once.

Design choices made while building (tell the user; open to change):
- `Property` also gets `SchemaPath`: the mapper's consolidated path (e.g.
  `ElectronBeam.WorkingDistance.Value`), so the export doesn't lose the mapping work for
  unmodelled values.
- An int fits a float field (same JSON number). null, a type mismatch, a value outside an enum
  or a taken slot -> Property.
- One source file = one dataset: shared singletons (`Image[0]`, `Instrument[0]`, ...) along each
  entity's shortest path from `OME`; an entity found as a dict merges into the first instance, a
  list's i-th item into the i-th.
- `Fluorescence_LightSource.Filament` in the mapper output -> profile entity
  `Fluorescence_LightSource_Filament` (category + title, when that is an entity name).
- `Tier` is a schema constant no source states: the converter makes it optional on every entity
  (was required on 100), rather than filling it in.

Current task (user): take refinements from imaging-metadata-converter without losing anything.
- Step 1: merge its mappings.json (18 new rules: TIFF/EXIF tags, full OME-shaped source, Stage.M,
  Microscope.SystemVacuum) into ours, keeping our rules it dropped (flat ome-tiff shape `objective.*`,
  `medium`, `refractive_index`) and the 5 Huygens rules - our sources/ keep the old shape (step 2,
  replacing sources/ with its examples, not requested). schema.extended.json: its 2 additions.
- Step 3: vendor tag wrappers (`FEI_TITAN`, `FibicsXML`, ...): rules match as if the wrapper were
  absent, the SourceMap keeps the full path, unmapped fields stay under the wrapper, collisions use
  the no-overwrite fallback. The converter's version lifts fields with setdefault (drops a value on
  a key collision, order dependent) and drops the wrapper key; on its own examples it silently loses
  EMSIS Xarosa's EXIF DateTimeDigitized (overwritten by OlympusSIS.datetime). Converter not changed.
- Progress (not committed): mappings merged (202 converter + 194 ours -> 212, insertions only, no
  general wildcard ahead of a more specific one); schema.extended.json = converter's (superset: the
  2 additions). Wrapper handling in `convert_metadata` + 4 synthetic tests; 55 tests pass. Only our
  Zeiss output changed (the new Stage.M and SystemVacuum rules). On the converter's 9 wrapped
  examples our mapper has 0 loss problems (exact SourceMap check); differences from the converter's
  output are all by design: unmapped fields stay under the wrapper, and EMSIS keeps both timestamps
  (EXIF DateTimeDigitized in Image.AcquisitionDate - first written wins - and OlympusSIS.datetime at
  its source path).

Extended profile (not committed): `models/schema.extended.yaml` (profile name LiMi-extended) =
fullSchema.yaml + what mappings/schema.extended.json adds beyond schema.json, generated by
`ProfileExtender` in src/ProfileConverter.py: `python src/main.py profile` writes it next to
fullSchema.yaml. Tests: ProfileExtenderTest (placement, nothing replaced, reachability, committed
file up to date - fails until the profile is regenerated after a schema.extended.json change) and
ExtendedProfileNoDataLossTest + declared-fields check on all sources. Not committed yet. Additions to a profile entity go on it
(Instrument, Image, ObjectiveSettings); non-entity categories become group entities under OME
(Detector, Software, SamplePositioning -> _Stage -> _Position ...); new top-level groups
(ElectronBeam, ElectronOptics, ElectronSource, Scan, Acquisition) under OME; nested names qualified
by path; number -> float, object -> string, array -> list of string; clashes skipped (OME's own
CustomProperties). 196 entities; every added entity gets an optional ID (is_identifier), as LiMi
entities have; metaseed: valid, no problems, no warnings (Hub draft LiMi-extended showed 5
identifier warnings before this). Export with `--profile models/schema.extended.yaml`: no loss on all 8 sources; typed values
e.g. Cikteq 5 -> 43, Phenom 8 -> 41, Zeiss 3 -> 44; TALOS 6 -> 18 (most TALOS metadata has no rule).

## TODO

- [ ] Map LiMi's per-property tier (1/2/3) to metaseed's advisory `tier` (required /
      recommended / optional), so real vendor files are not failed on tier-3 fields.
- [ ] Extension file for metadata beyond LiMi (EM groups first, seeded from the
      `schema.extended.json` additions), with an explicit `parent` per new entity.
- [ ] Unit normalisation (e.g. vendor "um" -> OME "µm") so unit fields can be typed; the
      original spelling must stay recoverable.
- [ ] Per-channel mapping (e.g. Huygens ChannelData[i] LambdaEx/LambdaEm -> each Channel's
      Fluorophore wavelengths): rules resolve from the root, so each channel's value collides.
- [ ] `medium`/`refractive_index` map to `Settings.ObjectiveSettings.Medium/RefractiveIndex`,
      which exist only in schema.extended.json, not LiMi (LiMi: ObjectiveSettings.ImmersionLiquid).
- [ ] Consider adding `DNAcropSmall.ome.json` (full OME + Huygens) as a source: a real test
      that mapped annotation values agree with the image's own OME values.
- [ ] Decide whether to delete the 9 unreachable entities (see Known issues).
- [ ] Open a PR for `metaseed-profile` (pushed).

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

Done so far (branch `metaseed-profile`, not pushed):
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

Open decision (ask the user): values placed in typed fields have no record of their source key,
and metaseed forbids extra keys. Options: provenance records in the dataset (a SourceMap-like
entity), or a `Property` copy of every source value beside the typed fields.

## TODO

- [ ] Map LiMi's per-property tier (1/2/3) to metaseed's advisory `tier` (required /
      recommended / optional), so real vendor files are not failed on tier-3 fields.
- [ ] Extension file for metadata beyond LiMi (EM groups first, seeded from the
      `schema.extended.json` additions), with an explicit `parent` per new entity.
- [ ] Decide whether to delete the 9 unreachable entities (see Known issues).
- [ ] Push `metaseed-profile` and open a PR.

# The imaging metadata model

How the imaging metadata model (`models/imaging.yaml`, version 1.0.0) was made, how it was extended
beyond LiMi with the metadata the source files hold (mostly electron microscopy), and how the model and
the datasets exported with it were validated.

## In short

- The model is a [LinkML](https://linkml.io) schema. It was converted from the LiMi XSD
  (4DN-BINA-OME, `models/LiMi_XMLSchema.xsd`, version 02.00), which itself extends the OME 2016-06
  data model. It is written in the style of the
  [OME LinkML schema](https://github.com/gouttegd/yamf-playground/blob/main/linkml/ome/ome.yaml):
  every field is defined once, on the class that owns it, and inherited by its subtypes.
- It is extended with what the source files hold beyond LiMi, mostly electron-microscopy metadata
  (electron beam, optics, source, scan, vacuum, stage positions, detector settings).
- `models/imaging.yaml` is the master: it is edited by hand. A metaseed profile is generated from it
  (`models/imaging.metaseed.yaml`, profile `imaging` 1.0), and so are the paths the mapper maps source
  metadata onto.
- The model is checked against the LinkML metamodel and against its sources (nothing of the XSD or of
  LiMi's JSON schemas is lost). The profile is checked by metaseed. All 13 example source files were
  converted, exported and validated with metaseed: the only errors left are LiMi's own required fields
  that the source files do not state.

## The files

| File | What it is |
|---|---|
| `models/imaging.yaml` | The master model: 248 classes (37 abstract), 136 enums, 71 types |
| `models/imaging_units.yaml` | The units enumerations (16), imported |
| `models/imaging_extension.yaml` | Metadata beyond LiMi, mostly EM (24 classes), imported |
| `models/imaging_provenance.yaml` | Where values came from, and values the model does not model (3 classes), imported |
| `models/imaging.metaseed.yaml` | The metaseed profile, generated (`python src/main.py metaseed`) |
| `models/LiMi_XMLSchema.xsd` | The LiMi XSD the model was converted from (reference, unchanged) |
| `models/fullSchema.json` | LiMi's JSON schemas (reference, unchanged) |
| `models/ome-2016-06.xsd` | The OME 2016-06 schema, source of descriptions LiMi leaves out |
| `mappings/mappings.json` | Rules from source keys to model paths |

## 1. From the LiMi XSD to a LinkML model

LiMi comes in two forms, and the XSD was chosen as the source.

- `fullSchema.json` (111 schemas, used by the Micro-Meta App) copies what it reuses. Each parent gets
  its own copy of a shared part (`Arc_IlluminationWavelengthRange`, seven copies of
  `TransmittanceRange`, ...), each light source role gets its own copy (`Transmitted_LightSource_Filament`
  and `Fluorescence_LightSource_Filament`, identical), and inherited fields are copied into every subtype.
  It also leaves out large parts of the XSD.
- The XSD defines each part once, has the inheritance (`extension base`), the abstract groups
  (substitution groups such as `LightSourceGroup`, `DetectorGroup`), the references (`*Ref`) and the
  enumerations. Its documentation holds each element's description and LiMi tier.

`python src/main.py linkml` (`src/LinkmlConverter.py`) converted the whole XSD once. The rules:

- A global element or named type becomes a class; its `extension base` becomes `is_a`. A substitution
  group member without a type of its own inherits the group's type.
- An abstract group becomes one slot over its (abstract) type, with a type designator:
  `Instrument.LightSource` holds Lasers, Arcs, Filaments, ... in one list.
- A `*Ref` becomes a reference to the target's ID (`inlined: false`), named without `Ref`, as in LiMi's
  JSON and the OME LinkML schema. The `ID` of a settings class refers to the component it configures.
- A type used by one element only is merged into that element's class; the type of an abstract group
  never is. A type reached only through an abstract group, or used only as a base, is abstract.
- Attributes and child elements become slots, with `required`, defaults (`ifabsent`), enumerations,
  patterns and bounds from the XSD. The units enumerations go to their own schema.
- The XSD's documentation becomes descriptions and annotations (`Tier`, `Category`, `Domain`, ...).
- LiMi's `Split` annotation, which says which roles a light source can play, becomes a `Role` field on
  `LightSource` (Transmitted, Fluorescence), limited per light source (a Laser is Fluorescence only),
  instead of the JSON's copy per role.

Descriptions the XSD leaves out were filled where a source exists, each marked with
`description_source`: 28 from the OME 2016-06 schema (CC BY 3.0, attributed in the model), and 265 derived
from the model itself (an enumeration from the slot that uses it, `XUnit` as "The unit of X"). The rest
(mostly enumeration values) stay empty rather than invented.

Slips in the XSD were worked around and recorded, keeping the original names as annotations: ID types
used by the wrong class, references whose ID attribute is not called `ID`, an attribute and an element of
the same name (`BeamSplitter.TransmittanceProfileFile`), an attribute named `ApertureNr.`, a typo
(`lluminationPowerSettingsUnit`). One class (`LightSensor`) is referenced but contained by nothing.

The converter is kept for comparing a future LiMi XSD; it does not overwrite the master.

Classes and fields that correspond to the OME LinkML schema carry `exact_mappings` or `close_mappings` to it
(prefix `ome:`): 21 classes (`Laser` is `ome:LaserLightSource`, ...) and 55 fields. A field named alike but
meaning something else is only close: OME's detector gain is a specification, the model's `Detector.Gain` a
vendor's per-image value. This keeps open making the model a formal extension of the OME LinkML schema.

## 2. Extensions beyond LiMi

The model was then extended by hand (every change is marked in the model with its source or reason).

**Metadata of the source files, mostly electron microscopy** (`models/imaging_extension.yaml`, formerly
the mapper's `schema.extended.json`). Fields for existing classes are LinkML mixins the model's classes
use; new groups are classes of their own:

| Where | What |
|---|---|
| Image | ElectronBeamSettings (type, mode, focus, spot size, working distance, acceleration voltage, currents, convergence angle, defocus, shift, source tilt, stigmator, high-voltage readings; the electron source it applies to), ElectronOpticsSettings (camera length, operating and projector modes, gun lens, apertures), ScanSettings (field of view, rotation, frame and line time, line integration, detector) |
| Instrument | Manufacturer, Model, Type, ComputerName, Vacuum (buffer, gun, sample, system vacuum, mode), ElectronSource (type) |
| Image | Type, CropHint, Corrections (contrast, brightness, gamma, black and white level) |
| Detector | Type, Gain, Offset, Brightness, Contrast, Channel, configuration |
| Stage | Position, RawPosition, Tilt, Rotation, Bias, MultiStage (sample height, radius) |
| Software | ApplicationID |

The EM groups follow LiMi's split between hardware and settings, as Objective and ObjectiveSettings do: the
electron source is part of the Instrument, and how the beam, the optics and the scan were set for an image
are that Image's `ElectronBeamSettings` (which refers to its electron source), `ElectronOpticsSettings` and
`ScanSettings`. The operator is LiMi's `Experimenter` (`UserName`), the start of acquisition
`Image.AcquisitionDate`.

A value with a unit (`WorkingDistance`, `FieldOfView.X`, ...) is one shared class, `Quantity`
{Value, Unit}, with the unit as the source writes it.

**Provenance** (`models/imaging_provenance.yaml`): `SourceFile` (name, SHA-256 checksum, format),
`SourceMapping` (which source key each typed value came from) and `Property` (a source value the model
does not model: its source path and JSON-encoded value), so that no metadata is lost.

**Choices made for real data:**

- `Image.AcquisitionDate` is a datetime, as in OME, where LiMi has a date: the sources give date and time.
  ISO 8601 variations are taken as they come, without conversion.
- IDs and references accept any string; the XSD's LSID patterns are kept as advisory annotations, so
  vendor IDs such as `SS1735` fit.
- A value for an abstract class goes into a default subtype, recorded on the class: LiMi's generic one
  (GenericDetector, GenericFilter, ...), or MechanicalStage for stages and AcquisitionSoftware for software.
- `OME.ID`/`Name` exist for metaseed datasets; `LightPath` got Tier 1 from LiMi's JSON (the XSD has none).

## 3. From the model to a metaseed profile

`python src/main.py metaseed` (`src/MetaseedGenerator.py`) writes the profile. metaseed has no
inheritance, so:

- every concrete class reachable from `OME` is an entity with its inherited fields written out (228 entities, 3667 fields);
- a slot over an abstract class becomes one field per subtype (`Instrument.Laser`, `Instrument.Arc`, ...);
  none of them can be required, since metaseed has no "one of";
- references are ID strings; enumerations, patterns and bounds become constraints;
- LiMi's tiers become metaseed tiers: the higher tier of the field and its class, tier 1 as
  `required`, 2 as `recommended`, 3 as `optional`. LiMi documents at these levels, so a field the XSD
  requires stays required only at tier 1.
- metaseed keys an entity by its `is_identifier` field, else by its first field that is not a reference.
  Where that field is optional free text, metaseed would warn, so the generator adds an optional `ID`;
  where it was required in the model and is optional only through its tier (StageLabel's `Name`), it is
  declared the identifier instead, so that a new version does not re-key existing datasets.

## 4. From source files to datasets

- `python src/main.py convert` (`src/AcquisitionMetadataMapper.py`) maps each source file onto model paths
  with the rules in `mappings/mappings.json` (235 rules) and `mappings/combinations.json`, falling back to
  matching source names against the model. Levels that only wrap a source's metadata (a vendor tag such
  as `FEI_TITAN.FeiImage`, or the root of a whole OME document) are left out of the paths the rules see. A
  value from a list item can go to the same item of a model list: a rule target
  `Pixels.Channel[*].Fluorophore.ExcitationWavelength` sends each channel's value to its own channel. A path starts at a class with an identifier and runs through
  its components: `Image.ElectronBeamSettings.WorkingDistance.Value`, `Pixels.PhysicalSizeX`,
  `MechanicalStage.Position.X.Value`. Unmapped keys stay at their source path; every value's source path
  is recorded.
- `python src/main.py export` (`src/DatasetExporter.py`) builds one metaseed dataset per source file. A
  value goes into a field only if it fits exactly (type, enumeration, format, free slot), with a
  `SourceMapping` naming its source key; anything else becomes a `Property` with its source path and
  value. Nothing is dropped. A unit spelled otherwise than the model spells it (`um`, `micrometre`) is
  stored as the model's unit (`µm`) when the units schema lists the spelling as an alias; the mapping
  keeps the source's spelling as `SourceValue`.

## 5. Validation

**The model**

- `linkml validate models/imaging.yaml`: valid against the LinkML metamodel. `linkml lint` reports only
  naming style (LiMi's PascalCase names are kept on purpose) and missing descriptions.
- Instance tests with the LinkML validator: an Instrument with a Laser and a Filament in one light-source
  list validates; a Laser with role Transmitted and a Filament with a laser field are rejected.
- Nothing lost from the sources (tests): everything a fresh conversion of the XSD yields is still in the
  master, with the same range (or the XSD's kept as `xsd_range` where a range was changed on purpose),
  and every property of `fullSchema.json` has a slot in the model. These tests were mutation-checked: a
  removed class, slot or enumeration value is reported. The extension was checked the same way when it
  was moved in: every field of `schema.extended.json` and every mapping target has a model path.
- No copies: shared parts (TransmittanceRange, IlluminationWavelengthRange, ...) exist once and are used
  by every parent.

**The profile**

- metaseed 0.54.0 `spec validate`: valid, no problems, no warnings; the same on the Hub, where profile
  profiles `imaging` 0.1 and 0.2 were published.
- Tests: every concrete class is reachable from OME (except LightSensor, which the XSD contains nowhere),
  and the committed profile is what the model generates.
- Each version against the one published before it, with metaseed's own compatibility check
  (`metaseed.specs.compare.compare_specs`), the check behind the Hub's "breaking changes": 0.2 against 0.1
  had none (458 fields no longer required through the tiers), so a minor version was enough. 1.0 against
  0.2 has 16, all intended, so it is a major version: the EM groups moved from OME into Instrument and Image
  (5 entities and 5 OME fields removed), ObjectiveSettings.Medium/RefractiveIndex removed (they are
  ImmersionLiquid's), the three UUID fields are strings with a pattern instead of URIs (metaseed failed on
  a pattern on a URI), and the electron source, now referable hardware, requires an ID.

**The datasets**

- The 13 source files in `sources/` (Cikteq, Delmic, EMSIS, TFS Phenom and two TALOS files, Zeiss,
  DICOM, two Leica LIF, OME-TIFF, a tomography file, Aperio SVS) were converted and exported, and every
  dataset validated with metaseed against the profile (the two TALOS files with their Property records
  sampled, since those are ~2,000-3,000 identical records). A Delmic dataset validated on the Hub gave
  exactly the local result.
- Result: no type, format, constraint or unknown-field error in any dataset. The only errors are required
  fields the source files do not state: 695 with every LiMi requirement enforced, of which 543 are tier 1
  (identifiers, names, pixel dimensions, objective and detector specifications) and remain with the tier
  mapping.
- No data lost (tests): every value of every source file is found again, with its type, at the path its
  source map names, and in the exported dataset as a typed field or a Property, both in memory and after
  writing. When the pipeline moved to this model, a comparison per source file also showed typed values
  plus Properties adding up to the same number as before.

## Reproducing

```
python src/main.py metaseed                                   # model -> models/imaging.metaseed.yaml
python src/main.py convert --input sources --output output    # sources -> model paths
python src/main.py export --input sources --output export     # -> metaseed datasets
python -m pytest                                              # all of the checks above
```

With the metaseed CLI (`pip install metaseed`): `metaseed spec import <draft> models/imaging.metaseed.yaml`,
`metaseed spec validate <draft>`, `metaseed spec save <draft>`, then
`metaseed validate export/<name>.yaml -p imaging -v 1.0 -e OME`.

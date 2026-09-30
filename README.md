# imaging-metadata-consolidator

**Decommissioned.** Everything this repository did now lives in
[imaging-metadata-converter](https://github.com/NL-BioImaging/imaging-metadata-converter): the mapper,
the imaging model (LinkML) and its mapping rules as the package, and the model's maintenance - the LiMi
XSD conversion, the metaseed profile (`imaging` 1.1 on the metaseed Hub) and the metaseed dataset
export - as scripts next to it. See its
[Maintaining the model](https://nl-bioimaging.github.io/imaging-metadata-converter/maintaining/) page.

Since model 1.1.0 the model's `id` names imaging-metadata-converter's URL. Profile 1.0 and model 1.0.0 still
name this repository's, which is why it stays, archived.

The `consolidate` command and the image readers (Consolidator, TiffSource, ImageSource) were not carried
over. The account of how the model was made is [docs/imaging-model.md](docs/imaging-model.md), as it
stood at the handover.

With metaseed 0.54.0, `metaseed validate` of a dataset against a large profile (1.2 MB YAML, 228 entities) takes 3.5-10 s per record; a dataset of about 3,000 records takes several hours.

Profiling one small dataset (29 records, 117 s) shows almost all the time in `SpecLoader._load_profile`: it ran 49 times, with 29 full `yaml.safe_load` parses of the profile at about 4 s each. The validation itself is negligible.

The cause: `create_engine_for_entity` (`validators/engine.py:739`) and several functions in `validators/api.py` (lines 118, 226, 277, 344) create a new `SpecLoader()` for each nested entity. `_profile_cache` is per instance, so it is always empty and the profile is parsed again every time.

Sharing one cache across loaders gives identical results in seconds: the 29-record dataset in 1.6 s instead of 44 s, and 13 datasets up to 3,000 records in 36 s in total. Our workaround:

```python
from metaseed.specs.loader import SpecLoader

shared_cache = {}
original_init = SpecLoader.__init__


def shared_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self._profile_cache = shared_cache


SpecLoader.__init__ = shared_init
```

Possible fixes: a module-level profile cache (keyed by path and modification time), passing one loader down through the nested validation, or reusing the loader across `_validate_nested` calls. Using libyaml's `CSafeLoader` where available would also cut the cost of each parse.

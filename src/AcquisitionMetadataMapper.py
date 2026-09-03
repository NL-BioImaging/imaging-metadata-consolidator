"""Map per-source acquisition metadata onto the consolidated schema.

Uses the field mappings in mappings/mappings.json to translate vendor-
specific metadata trees into the consolidated model defined by
mappings/schema.extended.json. This module works purely with in-memory
dicts; see convert.py for the reusable API that converts a single source
file with this module, and main.py for the CLI entry point.

Fields with no entry in mappings.json are matched against the schema itself
as a fallback, since some sources (e.g. OME-derived metadata) already use
field names that match the schema, just without a vendor-specific prefix.
"""

import json
from fnmatch import fnmatchcase


DEFAULT_SCHEMA_FILE = 'mappings/schema.extended.json'
DEFAULT_MAPPINGS_FILE = 'mappings/mappings.json'


class AcquisitionMetadataMapper:
    """Maps vendor-specific acquisition metadata onto the consolidated schema.

    Loads schema.extended.json and mappings.json once, then converts one or
    more metadata dicts using `convert_metadata`. Resolution for each field
    happens in two steps: first the explicit mappings.json rules (exact or
    "Prefix.*" wildcard), then, for anything left unmapped, a fallback match
    against the schema's own field names (e.g. standard OME metadata, which
    the schema is based on, already lines up with it directly). Fields that
    match neither step are kept at their original path so no data is lost.
    """

    def __init__(self, schema_file=DEFAULT_SCHEMA_FILE, mappings_file=DEFAULT_MAPPINGS_FILE):
        self.schema = self._load_json(schema_file)
        self.mappings = self._load_json(mappings_file)
        self._schema_index = self._build_schema_index(self.schema)

    @staticmethod
    def _load_json(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)

    @classmethod
    def _schema_leaf_paths(cls, schema, path=''):
        """Yield the dotted path of every leaf (non-dict) field in `schema`."""
        for key, value in schema.items():
            current = f'{path}.{key}' if path else key
            if isinstance(value, dict):
                yield from cls._schema_leaf_paths(value, current)
            else:
                yield current

    @classmethod
    def _build_schema_index(cls, schema):
        """Index every schema leaf path by each of its lowercase dotted suffixes.

        This lets an unmapped source path like "Pixels.SizeX" find the schema
        leaf "Image.Pixels.SizeX" without a vendor prefix. A suffix shared by
        more than one leaf (e.g. the many "Name"/"ID"/"Value" fields) is
        ambiguous and dropped, so it is never guessed at.
        """
        index = {}
        ambiguous = set()
        for full_path in cls._schema_leaf_paths(schema):
            components = full_path.split('.')
            for start in range(len(components)):
                suffix = tuple(part.lower() for part in components[start:])
                if suffix in index and index[suffix] != full_path:
                    ambiguous.add(suffix)
                else:
                    index[suffix] = full_path
        for suffix in ambiguous:
            del index[suffix]
        return index

    def _resolve_schema_path(self, source_path):
        """Resolve a dotted source path via the schema fallback, or None."""
        components = tuple(part.lower() for part in source_path.split('.'))
        return self._schema_index.get(components)

    def _resolve_wildcard_path(self, source_path):
        """Resolve a dotted source path via a "*"-containing mapping entry, or None.

        A pattern ending in ".*" remaps a whole subtree: the matched prefix
        is replaced by the target namespace and the remainder of the path is
        kept, so nested fields under the subtree keep their relative
        structure (e.g. "Beam.*" -> "ElectronBeam" turns "Beam.Focus" into
        "ElectronBeam.Focus").

        Any other "*"-containing pattern (e.g. one wildcarding a single,
        variable path segment such as "Annotation:...:Image:*") is treated
        as a whole-path match instead: on a match the target is the bare
        namespace with no remainder appended, since the varying segment
        (an index, a generated ID, ...) carries no information worth
        preserving in the consolidated schema.
        """
        for pattern, namespace in self.mappings.items():
            if '*' not in pattern or not fnmatchcase(source_path, pattern):
                continue
            if pattern.endswith('.*'):
                prefix = pattern[:-2]
                remainder = source_path[len(prefix) + 1:]
                return f'{namespace}.{remainder}' if remainder else namespace
            return namespace
        return None

    def _resolve_whole_segment_wildcard_path(self, source_path):
        """Resolve a dict's own path via a whole-segment wildcard entry, or None.

        Only patterns that do *not* end in ".*" are considered here. A
        ".*" pattern describes a subtree to expand field-by-field during
        recursion, so it must never collapse an intermediate dict early
        just because a *shallower* "Prefix.*" rule also happens to match
        that dict's own path — a more specific "Prefix.Sub.*" rule for one
        of its children would otherwise never get the chance to apply (see
        `_apply_mappings`). A pattern wildcarding a whole, variable path
        segment instead (e.g. an index or generated ID) has no such
        subtree semantics, so a match here collapses the entire dict as
        one opaque unit under the target namespace.
        """
        for pattern, namespace in self.mappings.items():
            if '*' not in pattern or pattern.endswith('.*'):
                continue
            if fnmatchcase(source_path, pattern):
                return namespace
        return None

    def _resolve_target_path(self, source_path):
        """Resolve a dotted source path to a dotted target path, or None.

        Tries mappings.json first: exact entries rename a single field, and
        wildcard entries remap a whole subtree or a single variable path
        segment (see `_resolve_wildcard_path`). Only when no mappings.json
        rule applies does this fall back to matching the path directly
        against the schema.
        """
        target = resolve_exact_path(source_path, self.mappings)
        if target is not None:
            return target

        target = self._resolve_wildcard_path(source_path)
        if target is not None:
            return target

        return self._resolve_schema_path(source_path)

    def _apply_mappings(self, metadata, result=None, path=''):
        """Map metadata onto the consolidated schema.

        Recurses into nested dictionaries, extending the dotted path as it
        goes, and writes every resolved field directly into the shared
        `result` dict. A dict is only moved as a whole (without recursing
        into it) when its own path has an exact or whole-segment wildcard
        mapping entry, so that a more specific "Prefix.Sub.*" rule for one
        of its children still gets the chance to apply, and so a shallower
        "Prefix.*" subtree rule never fires early on an intermediate node.
        Scalars and lists are always resolved (and placed) as a unit, using
        exact, embedded-metadata, wildcard or schema-fallback rules. Fields
        with no matching rule are kept at their original path so no data is
        silently dropped.
        """
        if result is None:
            result = {}
        for key, value in metadata.items():
            source_path = f'{path}.{key}' if path else str(key)
            if isinstance(value, dict):
                target_path = resolve_exact_path(source_path, self.mappings)
                if target_path is None:
                    target_path = self._resolve_whole_segment_wildcard_path(source_path)
                if target_path is not None:
                    set_nested_value(result, target_path, value)
                else:
                    self._apply_mappings(value, result, source_path)
            else:
                target_path = self._resolve_target_path(source_path)
                set_nested_value(result, target_path or source_path, value)
        return result

    def convert_metadata(self, metadata):
        """Map a single in-memory metadata dict onto the consolidated schema.

        Returns the converted dict.
        """
        if not isinstance(metadata, dict):
            raise TypeError('metadata must be a dict')

        return self._apply_mappings(metadata)

    def unmatched_fields(self, metadata):
        """List the output paths of leaf fields not represented in schema.extended.json.

        Converts `metadata`, then walks the *full* output and flags every
        leaf whose complete path is not itself a leaf declared in the
        schema. This deliberately looks past mappings.json's whole-segment
        wildcard rules (see `_resolve_whole_segment_wildcard_path`): a rule
        collapsing a vendor-specific subtree into a generic object-typed
        container (e.g. CustomProperties) makes conversion succeed, but the
        individual fields inside that subtree are still not modelled by the
        schema, so they must still count as unmatched here.
        """
        converted = self.convert_metadata(metadata)
        schema_leaf_paths = set(self._schema_leaf_paths(self.schema))

        unmatched = []

        def walk(node, path=''):
            for key, value in node.items():
                current = f'{path}.{key}' if path else str(key)
                if isinstance(value, dict):
                    walk(value, current)
                elif current not in schema_leaf_paths:
                    unmatched.append(current)

        walk(converted)
        return unmatched


def resolve_exact_path(source_path, mappings):
    """Resolve a dotted source path via an exact mapping entry, or None."""
    target = mappings.get(source_path)
    if target is not None:
        return target

    # TALOS-style processing operations can embed a second copy of
    # acquisition metadata below a generated operation UUID. Reuse the
    # canonical mapping for that suffix instead of adding another branch.
    metadata_marker = '.metadata.'
    if metadata_marker in source_path:
        embedded_path = source_path.split(metadata_marker, 1)[1]
        return resolve_exact_path(embedded_path, mappings)
    return None


def set_nested_value(target, dotted_path, value):
    keys = dotted_path.split('.')
    node = target
    for key in keys[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    node[keys[-1]] = value

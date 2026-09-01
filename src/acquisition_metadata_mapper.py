"""Convert per-source acquisition metadata into the consolidated schema.

Uses the field mappings in mappings/mappings.json to translate the vendor-
specific metadata trees under sources/ into the consolidated model, writing
one JSON file per source into output/.
"""

import argparse
import glob
import json
import os.path
from fnmatch import fnmatchcase


DEFAULT_OUTPUT_FORMAT = '.yaml'


def load_mappings(mappings_file):
    with open(mappings_file, 'r', encoding='utf-8') as file:
        return json.load(file)


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


def resolve_target_path(source_path, mappings):
    """Resolve a dotted source path to a dotted target path, or None.

    Exact entries rename a single field. Wildcard entries ("Prefix.*") remap
    a whole subtree: the matched prefix is replaced by the target namespace
    and the remainder of the path is kept, so nested fields under the
    subtree keep their relative structure.
    """
    target = resolve_exact_path(source_path, mappings)
    if target is not None:
        return target

    for pattern, namespace in mappings.items():
        if pattern.endswith('.*') and fnmatchcase(source_path, pattern):
            prefix = pattern[:-2]
            remainder = source_path[len(prefix) + 1:]
            return f'{namespace}.{remainder}' if remainder else namespace
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


def apply_mappings(metadata, mappings, result=None, path=''):
    """Map metadata onto the consolidated schema.

    Recurses into nested dictionaries, extending the dotted path as it goes,
    and writes every resolved field directly into the shared `result` dict.
    A dict is only moved as a whole (without recursing into it) when its own
    path has an exact mapping entry, so that a more specific mapping further
    down the tree still takes precedence over a shallower wildcard rule.
    Scalars and lists are always resolved (and placed) as a unit, using
    exact, embedded-metadata or wildcard rules. Fields with no matching rule
    are kept at their original path so no data is silently dropped.
    """
    if result is None:
        result = {}
    for key, value in metadata.items():
        source_path = f'{path}.{key}' if path else str(key)
        if isinstance(value, dict):
            target_path = resolve_exact_path(source_path, mappings)
            if target_path is not None:
                set_nested_value(result, target_path, value)
            else:
                apply_mappings(value, mappings, result, source_path)
        else:
            target_path = resolve_target_path(source_path, mappings)
            set_nested_value(result, target_path or source_path, value)
    return result


def read_metadata(input_file):
    """Read a metadata dict from `input_file`, choosing JSON or YAML by extension."""
    ext = os.path.splitext(input_file)[1].lower()
    with open(input_file, 'r', encoding='utf-8') as file:
        if ext in ('.yaml', '.yml'):
            import yaml
            return yaml.safe_load(file)
        return json.load(file)


def write_metadata(data, output_file):
    """Write `data` to `output_file`, choosing JSON or YAML by extension."""
    ext = os.path.splitext(output_file)[1].lower()
    os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as file:
        if ext in ('.yaml', '.yml'):
            import yaml
            yaml.dump(data, file, sort_keys=False, allow_unicode=True)
        else:
            json.dump(data, file, indent=2, default=str, ensure_ascii=False)


def convert_metadata(metadata, mappings, output_file=None):
    """Map a single in-memory metadata dict, optionally writing it out.

    Returns the converted dict. If `output_file` is given, it is also
    written there as JSON or YAML, chosen by its extension (.json, .yaml
    or .yml).
    """
    if not isinstance(metadata, dict):
        raise TypeError('metadata must be a dict')

    converted = apply_mappings(metadata, mappings)

    if output_file is not None:
        write_metadata(converted, output_file)

    return converted


def convert_file(input_file, mappings, output_file):
    metadata = read_metadata(input_file)
    convert_metadata(metadata, mappings, output_file)
    return output_file


def convert_sources(input_dir, output_dir, mappings_file):
    mappings = load_mappings(mappings_file)
    input_files = sorted(
        file for extension in ('.json', '.yaml', '.yml')
        for file in glob.glob(os.path.join(input_dir, f'*{extension}'))
    )
    output_files = []
    for input_file in input_files:
        name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir, name + DEFAULT_OUTPUT_FORMAT)
        output_files.append(convert_file(input_file, mappings, output_file))
    return output_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True,
                        help='Folder of source metadata files')
    parser.add_argument('--output', required=True,
                        help='Folder to write converted files to')
    parser.add_argument('--mappings', required=True,
                        help='Path to mappings.json')
    args = parser.parse_args()

    output_files = convert_sources(args.input, args.output, args.mappings)
    for output_file in output_files:
        print(f'Wrote {output_file}')


if __name__ == '__main__':
    convert_sources('sources', 'output/', 'mappings/mappings.json')

import yaml


def serialise_yaml(data):
    return yaml.dump(data)


def deserialise_yaml(string):
    return yaml.safe_load(string)

from datetime import datetime

import json


class CustomEncoder(json.JSONEncoder):
    def default(self, value):
        if isinstance(value, datetime):
            return str(value)
        return super().default(value)


def serialise_json(data):
    return json.dumps(data, cls=CustomEncoder)


def deserialise_json(string):
    return json.loads(string)

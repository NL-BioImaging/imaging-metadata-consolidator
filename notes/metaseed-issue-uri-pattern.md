A profile field of type `uri` with a `pattern` constraint fails validation for every value, including valid ones:

```yaml
- name: UUID
  type: uri
  constraints:
    pattern: (urn:uuid:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})
```

Validating the value `urn:uuid:69658110-5216-4e10-95c3-b1bdca2a1e52` with metaseed 0.54.0 fails with:

```
ValidationError: 1 validation error for ValidatorCallable
  Input should be a valid string [type=string_type,
input_value=AnyUrl('urn:uuid:69658110...4e10-95c3-b1bdca2a1e52'), input_type=AnyUrl]
```

The pattern is applied to the parsed `AnyUrl` instead of the string. We work around it by generating such fields as `type: string` with the pattern.

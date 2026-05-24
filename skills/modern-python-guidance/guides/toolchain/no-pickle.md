---
id: no-pickle
title: Avoid pickle for Untrusted Data
category: toolchain
layer: 3
tags:
  - security
  - serialization
  - pickle
aliases:
  - pickle
  - unpickle
  - pickle.load
  - shelve
python: ">=3.9"
frequency: medium
---

# Avoid pickle for Untrusted Data

`pickle.load()` executes arbitrary code during deserialization. Never use it with untrusted data.

## BAD

```python
import pickle

def load_model(path: str):
    with open(path, "rb") as f:
        return pickle.load(f)  # arbitrary code execution

def cache_result(data, path: str):
    with open(path, "wb") as f:
        pickle.dump(data, f)
```

## GOOD

```python
import json

def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)

# For structured data
import msgpack  # or orjson, cbor2

def load_data(path: str) -> dict:
    with open(path, "rb") as f:
        return msgpack.unpack(f)

# For ML models — use framework-native formats
import torch
model = torch.load(path, weights_only=True)  # safe mode
```

## Why

- `pickle.load()` can execute arbitrary Python code — a known RCE vector
- Applies to `pickle`, `shelve`, `marshal`, and any library using pickle internally
- JSON, MessagePack, CBOR are safe — they only deserialize data, not code
- ML frameworks provide safe alternatives (`weights_only=True`, ONNX, SafeTensors)
- Python's own docs warn: "Never unpickle data received from an untrusted source"

## Safe Alternatives

| Use case | Recommended format |
|----------|-------------------|
| Configuration | JSON, TOML, YAML |
| Structured data | JSON, MessagePack, Protocol Buffers |
| DataFrames | Parquet, CSV |
| ML models | SafeTensors, ONNX, `weights_only=True` |
| Caching | JSON + compression, Redis |

## References

- [Python docs — pickle security](https://docs.python.org/3/library/pickle.html#restricting-globals)
- [CWE-502: Deserialization of Untrusted Data](https://cwe.mitre.org/data/definitions/502.html)

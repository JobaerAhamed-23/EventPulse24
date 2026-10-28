"""AD-4: embeddings never decide identity, so no domain API even accepts one."""

import dataclasses
import importlib
import inspect
import pkgutil

import domain

FORBIDDEN = ("embed", "cosine", "vector", "similar")


def _public_names():
    for info in pkgutil.walk_packages(domain.__path__, "domain."):
        module = importlib.import_module(info.name)
        for name, obj in vars(module).items():
            if name.startswith("_") or getattr(obj, "__module__", None) != module.__name__:
                continue
            yield f"{info.name}.{name}", name
            if dataclasses.is_dataclass(obj):
                yield from (
                    (f"{info.name}.{name}.{f.name}", f.name) for f in dataclasses.fields(obj)
                )
            if inspect.isfunction(obj):
                params = inspect.signature(obj).parameters
                yield from ((f"{info.name}.{name}({p})", p) for p in params)


def test_no_domain_api_takes_an_embedding_or_similarity_input():
    names = list(_public_names())

    assert names  # the scan found the API
    assert [where for where, name in names if any(w in name.lower() for w in FORBIDDEN)] == []

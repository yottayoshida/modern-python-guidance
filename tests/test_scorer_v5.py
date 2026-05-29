"""Tests for bench/score_v5.py — AST-based benchmark scorer V5.

Requires Python 3.12+. The scorer uses AST features and fixture code
that may produce different results on 3.11.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

if sys.version_info < (3, 12):
    pytest.skip("scorer V5 requires Python 3.12+", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bench.score_v5 import (
    CheckResult,
    ParsedFile,
    check_AS1,
    check_AS2,
    check_AS3,
    check_DJ1,
    check_DJ2,
    check_DJ3,
    check_DS1,
    check_DS2,
    check_DS3,
    check_FA1,
    check_FA2,
    check_HX1,
    check_HX2,
    check_PD1,
    check_PD2,
    check_PD4,
    check_PT1,
    check_PT2,
    check_PT3,
    check_SA1,
    check_SA2,
    check_SA3,
    check_SL1,
    check_SL2,
    check_SL3,
    check_SL4,
    check_TC3,
    check_TC4,
    check_TY1,
    check_TY2,
    check_TY3,
    check_TY4,
    check_TY5,
    check_TY6,
    parse_file,
    score_session,
)

REPO_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_files(tmp_path: Path, code: str, filename: str = "test_code.py") -> list[ParsedFile]:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(code))
    pf = parse_file(p)
    return [pf] if pf else []


# ---------------------------------------------------------------------------
# Fixture parity: existing 6 fixture sets must match V4 scorer results
# ---------------------------------------------------------------------------


class TestFixtureParity:
    """V5 AST scorer must agree with V4 grep scorer on existing fixtures.

    Expected deltas for VALID_ALT items (SA2, TY6) are documented:
    V4 scored them as OUTDATED; V5 scores them as VALID_ALT.
    """

    def test_variant_a_modern(self):
        data = score_session(REPO_DIR / "bench/fixtures/variant-a-modern", "a")
        assert data["modern"] == 32
        assert data["outdated"] == 0

    def test_variant_a_outdated(self):
        data = score_session(REPO_DIR / "bench/fixtures/variant-a-outdated", "a")
        assert data["modern"] == 0
        # SA2 and TY6 are VALID_ALT in V5 (were OUTDATED in V4)
        assert data["valid_alt"] == 2
        items = data["items"]
        assert items["SA2"]["result"] == "VALID_ALT"
        assert items["TY6"]["result"] == "VALID_ALT"

    def test_variant_b_modern(self):
        data = score_session(REPO_DIR / "bench/fixtures/variant-b-modern", "b")
        assert data["modern"] == 3

    def test_variant_b_outdated(self):
        data = score_session(REPO_DIR / "bench/fixtures/variant-b-outdated", "b")
        assert data["outdated"] == 3

    def test_variant_c_modern(self):
        data = score_session(REPO_DIR / "bench/fixtures/variant-c-modern", "c")
        assert data["modern"] == 3

    def test_variant_c_outdated(self):
        data = score_session(REPO_DIR / "bench/fixtures/variant-c-outdated", "c")
        assert data["modern"] == 0


# ---------------------------------------------------------------------------
# Edge cases: Opus 4.8 style + VALID_ALT + error handling
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_opus48_multiline_tc3(self):
        pf = parse_file(REPO_DIR / "bench/fixtures/edge-cases/opus48_multiline.py")
        assert check_TC3([pf]) == CheckResult.MODERN

    def test_opus48_multiline_as1(self):
        pf = parse_file(REPO_DIR / "bench/fixtures/edge-cases/opus48_multiline.py")
        assert check_AS1([pf]) == CheckResult.MODERN

    def test_opus48_multiline_ty6(self):
        pf = parse_file(REPO_DIR / "bench/fixtures/edge-cases/opus48_multiline.py")
        assert check_TY6([pf]) == CheckResult.VALID_ALT

    def test_valid_alt_sa2(self):
        pf = parse_file(REPO_DIR / "bench/fixtures/edge-cases/valid_alt_patterns.py")
        assert check_SA2([pf]) == CheckResult.VALID_ALT

    def test_valid_alt_ty6(self):
        pf = parse_file(REPO_DIR / "bench/fixtures/edge-cases/valid_alt_patterns.py")
        assert check_TY6([pf]) == CheckResult.VALID_ALT

    def test_valid_alt_as3(self):
        pf = parse_file(REPO_DIR / "bench/fixtures/edge-cases/valid_alt_patterns.py")
        assert check_AS3([pf]) == CheckResult.VALID_ALT

    def test_syntax_error_returns_none(self, tmp_path):
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(")
        pf = parse_file(bad)
        assert pf is None

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.py"
        empty.write_text("")
        files = _make_files(tmp_path, "", "empty2.py")
        assert check_AS1(files) == CheckResult.NONE

    def test_docstring_with_outdated_keyword(self, tmp_path):
        code = '''
        import subprocess
        def run(cmd):
            """Never use os.system() or shell=True."""
            return subprocess.run([cmd], check=True)
        '''
        files = _make_files(tmp_path, code)
        assert check_TC3(files) == CheckResult.MODERN


# ---------------------------------------------------------------------------
# Per-item golden tests: inline code snippets
# ---------------------------------------------------------------------------


class TestAS:
    def test_as1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import asyncio
        async def f():
            async with asyncio.TaskGroup() as tg:
                tg.create_task(g())
        """,
        )
        assert check_AS1(files) == CheckResult.MODERN

    def test_as1_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import asyncio
        async def f():
            await asyncio.gather(a(), b())
        """,
        )
        assert check_AS1(files) == CheckResult.OUTDATED

    def test_as2_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import asyncio
        async def f():
            async with asyncio.timeout(30):
                await do_work()
        """,
        )
        assert check_AS2(files) == CheckResult.MODERN

    def test_as2_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import asyncio
        async def f():
            await asyncio.wait_for(do_work(), timeout=30)
        """,
        )
        assert check_AS2(files) == CheckResult.OUTDATED

    def test_as3_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import asyncio
        async def f():
            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(g())
            except* OSError:
                pass
        """,
        )
        assert check_AS3(files) == CheckResult.MODERN

    def test_as3_none(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def f():
            pass
        """,
        )
        assert check_AS3(files) == CheckResult.NONE


class TestDS:
    def test_ds1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from dataclasses import dataclass
        @dataclass(frozen=True, slots=True)
        class Point:
            x: float
            y: float
        """,
        )
        assert check_DS1(files) == CheckResult.MODERN

    def test_ds1_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from dataclasses import dataclass
        @dataclass
        class Point:
            x: float
            y: float
        """,
        )
        assert check_DS1(files) == CheckResult.OUTDATED

    def test_ds2_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def merge(a: dict, b: dict) -> dict:
            return a | b
        """,
        )
        assert check_DS2(files) == CheckResult.MODERN

    def test_ds2_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def merge(a: dict, b: dict) -> dict:
            return {**a, **b}
        """,
        )
        assert check_DS2(files) == CheckResult.OUTDATED

    def test_ds2_type_union_not_detected(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def f(x: int | str) -> None:
            pass
        """,
        )
        assert check_DS2(files) == CheckResult.NONE

    def test_ds3_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def categorize(ext):
            match ext:
                case ".jpg" | ".png":
                    return "image"
                case _:
                    return "other"
        """,
        )
        assert check_DS3(files) == CheckResult.MODERN

    def test_ds3_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def categorize(x):
            if isinstance(x, int):
                return "int"
            elif isinstance(x, str):
                return "str"
            else:
                return "other"
        """,
        )
        assert check_DS3(files) == CheckResult.OUTDATED


class TestFA:
    def test_fa1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from fastapi import FastAPI
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def lifespan(app):
            yield
        app = FastAPI(lifespan=lifespan)
        """,
        )
        assert check_FA1(files) == CheckResult.MODERN

    def test_fa1_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from fastapi import FastAPI
        app = FastAPI()
        @app.on_event("startup")
        async def startup():
            pass
        """,
        )
        assert check_FA1(files) == CheckResult.OUTDATED

    def test_fa2_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from typing import Annotated
        from fastapi import Depends
        DbDep = Annotated[Session, Depends(get_db)]
        """,
        )
        assert check_FA2(files) == CheckResult.MODERN

    def test_fa2_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from fastapi import Depends
        async def endpoint(db = Depends(get_db)):
            pass
        """,
        )
        assert check_FA2(files) == CheckResult.OUTDATED


class TestHX:
    def test_hx1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import httpx
        async def f():
            async with httpx.AsyncClient() as client:
                await client.get("http://example.com")
        """,
        )
        assert check_HX1(files) == CheckResult.MODERN

    def test_hx1_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import httpx
        def f():
            r = httpx.get("http://example.com")
        """,
        )
        assert check_HX1(files) == CheckResult.OUTDATED

    def test_hx2_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import httpx
        async def f(client):
            async with client.stream("GET", url) as resp:
                async for chunk in resp.aiter_bytes():
                    pass
        """,
        )
        assert check_HX2(files) == CheckResult.MODERN


class TestPD:
    def test_pd1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from pydantic import BaseModel, ConfigDict
        class User(BaseModel):
            model_config = ConfigDict(from_attributes=True)
            name: str
        """,
        )
        assert check_PD1(files) == CheckResult.MODERN

    def test_pd1_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from pydantic import BaseModel
        class User(BaseModel):
            class Config:
                orm_mode = True
            name: str
        """,
        )
        assert check_PD1(files) == CheckResult.OUTDATED

    def test_pd2_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from pydantic import BaseModel
        class User(BaseModel):
            name: str
        u = User.model_validate({"name": "Alice"})
        d = u.model_dump()
        """,
        )
        assert check_PD2(files) == CheckResult.MODERN

    def test_pd2_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from pydantic import BaseModel
        class User(BaseModel):
            name: str
        u = User.parse_obj({"name": "Alice"})
        d = u.dict()
        """,
        )
        assert check_PD2(files) == CheckResult.OUTDATED

    def test_pd4_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from pydantic import BaseModel, field_validator
        class User(BaseModel):
            name: str
            @field_validator("name")
            @classmethod
            def check_name(cls, v):
                return v
        """,
        )
        assert check_PD4(files) == CheckResult.MODERN

    def test_pd4_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from pydantic import BaseModel, validator
        class User(BaseModel):
            name: str
            @validator("name")
            def check_name(cls, v):
                return v
        """,
        )
        assert check_PD4(files) == CheckResult.OUTDATED


class TestSA:
    def test_sa1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from sqlalchemy import select
        def get_users(session):
            return session.execute(select(User)).scalars().all()
        """,
        )
        assert check_SA1(files) == CheckResult.MODERN

    def test_sa1_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from sqlalchemy.orm import Session
        def get_users(session):
            return session.query(User).all()
        """,
        )
        assert check_SA1(files) == CheckResult.OUTDATED

    def test_sa3_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from sqlalchemy.orm import Mapped, mapped_column
        class User:
            id: Mapped[int] = mapped_column(primary_key=True)
        """,
        )
        assert check_SA3(files) == CheckResult.MODERN

    def test_sa3_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from sqlalchemy import Column, Integer
        class User:
            id = Column(Integer, primary_key=True)
        """,
        )
        assert check_SA3(files) == CheckResult.OUTDATED


class TestSL:
    def test_sl1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from datetime import datetime, UTC
        now = datetime.now(UTC)
        """,
        )
        assert check_SL1(files) == CheckResult.MODERN

    def test_sl1_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from datetime import datetime
        now = datetime.utcnow()
        """,
        )
        assert check_SL1(files) == CheckResult.OUTDATED

    def test_sl2_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from pathlib import Path
        p = Path("/tmp") / "file.txt"
        """,
        )
        assert check_SL2(files) == CheckResult.MODERN

    def test_sl2_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import os
        p = os.path.join("/tmp", "file.txt")
        """,
        )
        assert check_SL2(files) == CheckResult.OUTDATED

    def test_sl3_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def strip(line):
            return line.removeprefix("[INFO] ")
        """,
        )
        assert check_SL3(files) == CheckResult.MODERN

    def test_sl3_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def strip(line, prefix):
            return line[len(prefix):]
        """,
        )
        assert check_SL3(files) == CheckResult.OUTDATED

    def test_sl4_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import tomllib
        with open("config.toml", "rb") as f:
            data = tomllib.load(f)
        """,
        )
        assert check_SL4(files) == CheckResult.MODERN

    def test_sl4_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import toml
        data = toml.load("config.toml")
        """,
        )
        assert check_SL4(files) == CheckResult.OUTDATED


class TestTC:
    def test_tc3_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import subprocess
        subprocess.run(["ls", "-la"], check=True)
        """,
        )
        assert check_TC3(files) == CheckResult.MODERN

    def test_tc3_outdated_os_system(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import os
        os.system("ls -la")
        """,
        )
        assert check_TC3(files) == CheckResult.OUTDATED

    def test_tc3_outdated_shell_true(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import subprocess
        subprocess.run("ls -la", shell=True)
        """,
        )
        assert check_TC3(files) == CheckResult.OUTDATED

    def test_tc4_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import json
        data = json.loads('{"key": "value"}')
        """,
        )
        assert check_TC4(files) == CheckResult.MODERN

    def test_tc4_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import pickle
        data = pickle.loads(b"data")
        """,
        )
        assert check_TC4(files) == CheckResult.OUTDATED


class TestTY:
    def test_ty1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def f(items: list[str]) -> dict[str, int]:
            return {}
        """,
        )
        assert check_TY1(files) == CheckResult.MODERN

    def test_ty1_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from typing import List, Dict
        def f(items: List[str]) -> Dict[str, int]:
            return {}
        """,
        )
        assert check_TY1(files) == CheckResult.OUTDATED

    def test_ty2_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def f(x: int | None) -> str | int:
            return x
        """,
        )
        assert check_TY2(files) == CheckResult.MODERN

    def test_ty2_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from typing import Optional
        def f(x: Optional[int]) -> int:
            return x
        """,
        )
        assert check_TY2(files) == CheckResult.OUTDATED

    @pytest.mark.skipif(sys.version_info < (3, 12), reason="type parameter syntax requires 3.12+")
    def test_ty3_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        class Stack[T]:
            def push(self, item: T) -> None:
                pass
        """,
        )
        assert check_TY3(files) == CheckResult.MODERN

    def test_ty3_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from typing import TypeVar
        T = TypeVar("T")
        class Stack:
            pass
        """,
        )
        assert check_TY3(files) == CheckResult.OUTDATED

    def test_ty4_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from typing import override
        class Child(Base):
            @override
            def method(self):
                pass
        """,
        )
        assert check_TY4(files) == CheckResult.MODERN

    def test_ty5_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from typing import ParamSpec
        P = ParamSpec("P")
        """,
        )
        assert check_TY5(files) == CheckResult.MODERN

    def test_ty5_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from typing import Any
        def decorator(func):
            def wrapper(*args: Any, **kwargs: Any):
                return func(*args, **kwargs)
            return wrapper
        """,
        )
        assert check_TY5(files) == CheckResult.OUTDATED

    def test_ty6_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from typing import TypeIs
        def is_str(val: object) -> TypeIs[str]:
            return isinstance(val, str)
        """,
        )
        assert check_TY6(files) == CheckResult.MODERN

    def test_ty6_valid_alt(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from typing import TypeGuard
        def is_str(val: object) -> TypeGuard[str]:
            return isinstance(val, str)
        """,
        )
        assert check_TY6(files) == CheckResult.VALID_ALT


class TestDJ:
    def test_dj1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from django.db import models
        class Product(models.Model):
            data = models.JSONField(default=dict)
        """,
        )
        assert check_DJ1(files) == CheckResult.MODERN

    def test_dj2_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from django.db import models
        class Meta:
            constraints = [
                models.CheckConstraint(condition=models.Q(price__gte=0), name="p")
            ]
        """,
        )
        assert check_DJ2(files) == CheckResult.MODERN

    def test_dj2_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from django.db import models
        class Meta:
            constraints = [
                models.CheckConstraint(check=models.Q(price__gte=0), name="p")
            ]
        """,
        )
        assert check_DJ2(files) == CheckResult.OUTDATED

    def test_dj3_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from django.http import JsonResponse
        async def product_list(request):
            products = []
            async for p in Product.objects.all():
                products.append(p)
            return JsonResponse({"products": products})
        """,
        )
        assert check_DJ3(files) == CheckResult.MODERN

    def test_dj3_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from asgiref.sync import sync_to_async
        from django.http import JsonResponse
        async def product_list(request):
            products = await sync_to_async(get_products)()
            return JsonResponse({"products": products})
        """,
        )
        assert check_DJ3(files) == CheckResult.OUTDATED


class TestPT:
    def test_pt1_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import pytest
        @pytest.mark.parametrize("x,y", [(1,2), (3,4)])
        def test_add(x, y):
            assert x + y > 0
        """,
        )
        assert check_PT1(files) == CheckResult.MODERN

    def test_pt2_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import pytest
        def test_div():
            with pytest.raises(ZeroDivisionError, match="division"):
                1 / 0
        """,
        )
        assert check_PT2(files) == CheckResult.MODERN

    def test_pt2_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import pytest
        def test_div():
            with pytest.raises(ZeroDivisionError):
                1 / 0
        """,
        )
        assert check_PT2(files) == CheckResult.OUTDATED

    def test_pt3_modern(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def test_write(tmp_path):
            f = tmp_path / "test.txt"
            f.write_text("hello")
        """,
        )
        assert check_PT3(files) == CheckResult.MODERN

    def test_pt3_outdated(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        def test_write(tmpdir):
            f = tmpdir.join("test.txt")
            f.write("hello")
        """,
        )
        assert check_PT3(files) == CheckResult.OUTDATED


# ---------------------------------------------------------------------------
# Import alias handling
# ---------------------------------------------------------------------------


class TestImportAlias:
    def test_aliased_subprocess(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        import subprocess as sp
        sp.run(["ls"], check=True)
        """,
        )
        assert check_TC3(files) == CheckResult.MODERN

    def test_from_import_alias(self, tmp_path):
        files = _make_files(
            tmp_path,
            """
        from asyncio import TaskGroup as TG
        async def f():
            async with TG() as tg:
                pass
        """,
        )
        # TaskGroup detection checks ast.Name/ast.Attribute, alias tracking
        # ensures the import is recognized
        assert check_AS1(files) == CheckResult.MODERN


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


class TestJSONOutput:
    def test_score_session_returns_dict(self):
        data = score_session(REPO_DIR / "bench/fixtures/variant-a-modern", "a")
        assert isinstance(data, dict)
        assert "modern" in data
        assert "items" in data
        assert "strict_modern_pct" in data
        assert "inclusive_modern_pct" in data
        assert "v4_compat_score_pct" in data

    def test_dual_reporting(self):
        data = score_session(REPO_DIR / "bench/fixtures/variant-a-outdated", "a")
        assert data["strict_modern_pct"] >= 0
        assert data["inclusive_modern_pct"] >= 0
        # Inclusive should be >= strict (VALID_ALT adds to numerator)
        assert data["inclusive_modern_pct"] >= data["strict_modern_pct"]

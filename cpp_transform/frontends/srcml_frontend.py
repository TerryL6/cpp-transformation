"""srcML-backed frontend: lossless parse (source -> srcML XML) and unparse.

Implementation notes
--------------------
* Uses the ``srcml`` binary via subprocess with stdin/stdout so we never write
  temp files or leak a ``filename`` attribute into the XML.
* ``parse`` requires an explicit ``language`` ("C" or "C++"); language detection
  is the dataset layer's responsibility (we never silently guess here).
* ``unparse`` serializes the lxml tree to srcML XML and feeds it back to
  ``srcml``; srcML auto-detects XML input and emits source. This keeps output
  generation strictly tree-driven.
* The binary path and ``LD_LIBRARY_PATH`` are configurable so the framework
  works regardless of how srcml was installed (env: ``SRCML_BIN``/``SRCML_LIB``).
"""

from __future__ import annotations

import os
import subprocess

from lxml import etree

from .base import Frontend, FrontendError

_LANG_FLAG = {"C": "C", "C++": "C++", "CPP": "C++", "CXX": "C++"}


class SrcmlFrontend(Frontend):
    def __init__(
        self,
        srcml_bin: str | None = None,
        lib_path: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.srcml_bin = srcml_bin or os.environ.get("SRCML_BIN", "srcml")
        self.lib_path = lib_path or os.environ.get("SRCML_LIB")
        self.timeout = timeout

    # -- subprocess plumbing ------------------------------------------------
    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.lib_path:
            prev = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = (
                f"{self.lib_path}:{prev}" if prev else self.lib_path
            )
        return env

    def _run(self, args: list[str], stdin_bytes: bytes) -> bytes:
        try:
            proc = subprocess.run(
                [self.srcml_bin, *args],
                input=stdin_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env(),
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise FrontendError(
                f"srcml binary not found: {self.srcml_bin!r}. "
                f"Set SRCML_BIN or pass --srcml-bin."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise FrontendError(f"srcml timed out after {self.timeout}s") from exc
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise FrontendError(f"srcml failed (rc={proc.returncode}): {err}")
        return proc.stdout

    def _normalize_language(self, language: str) -> str:
        key = (language or "").strip()
        if key not in _LANG_FLAG:
            raise FrontendError(
                f"unsupported/unknown language {language!r}; expected C or C++"
            )
        return _LANG_FLAG[key]

    # -- Frontend API -------------------------------------------------------
    def parse(self, code: str, language: str) -> etree._Element:
        lang = self._normalize_language(language)
        xml = self._run(["--language", lang, "-"], code.encode("utf-8"))
        parser = etree.XMLParser(huge_tree=True, recover=False)
        try:
            root = etree.fromstring(xml, parser=parser)
        except etree.XMLSyntaxError as exc:  # pragma: no cover - defensive
            raise FrontendError(f"could not parse srcML output: {exc}") from exc
        return root

    def unparse(self, unit: etree._Element) -> str:
        xml_bytes = etree.tostring(unit, encoding="UTF-8", xml_declaration=True)
        out = self._run(["-"], xml_bytes)
        return out.decode("utf-8")

    def version(self) -> str:
        return self._run(["--version"], b"").decode("utf-8", errors="replace").strip()

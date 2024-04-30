"""
Functions to analyze static and dynamic libraries to identify dependencies.
"""

from pathlib import PurePath, Path
import re
import subprocess
from conan_barbarian.data import Cache


NM_REGEX = re.compile(r'^(?:[0-9a-f]{16})?\s+(?P<type>[AcBbCcDdGgRrSsTtUuVvWw])\s+(?P<symbol>.*)$')

def _parse_nm_output(nm_output: str):
    defined_symbols = []
    undefined_symbols = []
    for line in nm_output.splitlines():
        if (match := NM_REGEX.match(line)):
            stype, symbol = match.groups()
            # (T)text, (R)read-only, (W)weak, (B)bss area
            if stype in ['T', 'R', 'W', 'B']:
                defined_symbols.append(symbol)
            elif stype == 'U':  # (U)undefined
                undefined_symbols.append(symbol)
    undefined_symbols = [us for us in undefined_symbols if us not in defined_symbols]
    return defined_symbols, undefined_symbols


def _update_cache(cache: Cache, libname: str, defined: list[str], undefined: list[str], package=None):
    cache.add_library(libname, package=package)

    for symbol in defined:
        depending_libs = cache.define_symbol(symbol, libname)
        for dl in depending_libs:
            cache.add_dependency(dl, libname)

    for symbol in undefined:
        definer = cache.get_library_defining_symbol(symbol)
        if definer:
            cache.add_dependency(libname, definer)
        else:
            cache.add_undefined_symbol_dependency(symbol, libname)


def analyze_library(library_path: Path, cache: Cache, *, package=None):
    suffix = library_path.suffix
    libname = library_path.name

    if suffix == '.a':
        cmd = ['nm', '-C', str(library_path)]
    elif suffix == '.so':
        cmd = ['nm', '-C', '-D', str(library_path)]
    else:
        raise Exception(f'Invalid library path {library_path}')
    
    cp = subprocess.run(cmd, capture_output=True, text=True)
    defined, undefined = _parse_nm_output(cp.stdout)
    _update_cache(cache, libname, defined, undefined, package)

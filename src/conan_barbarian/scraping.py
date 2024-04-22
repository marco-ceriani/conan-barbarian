"""
Functions to analyze static and dynamic libraries to identify dependencies.
"""

from pathlib import PurePath
import re
import subprocess
from conan_barbarian.data import Cache


NM_REGEX = re.compile(r'^(?:[0-9a-f]{16})?\s+(?P<type>[AcBbCcDdGgRrSsTtUuVvWw])\s+(?P<symbol>.*)$')

def _parse_nm_output(nm_output):
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
    return defined_symbols, undefined_symbols


def analyze_library(library_path: str, cache: Cache):
    pp = PurePath(library_path)
    suffix = pp.suffix
    libname = pp.name

    if suffix == '.a':
        cmd = ['nm', '-C', library_path]
    elif suffix == '.so':
        cmd = ['nm', '-C', '-D', library_path]
    else:
        raise Exception('Invalid library path ' + library_path)
    
    cp = subprocess.run(cmd, capture_output=True, text=True)
    defined, undefined = _parse_nm_output(cp.stdout)

    cache.add_library(libname)

    for symbol in defined:
        cache.define_symbol(symbol, libname)
        depending_libs = cache.define_symbol(symbol, libname)
        for dl in depending_libs:
            cache.add_dependency(dl, libname)

    for symbol in undefined:
        definer = cache.get_library_defining_symbol(symbol)
        if definer:
            cache.add_dependency(libname, definer)
        else:
            cache.undefined_symbols.setdefault(symbol, set()).add(libname)

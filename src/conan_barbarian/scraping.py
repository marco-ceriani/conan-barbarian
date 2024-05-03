"""
Functions to analyze static and dynamic libraries to identify dependencies.
"""

from pathlib import Path
import re
import subprocess
import logging
from conan_barbarian.data import Cache


logger = logging.getLogger(__name__)

NM_REGEX = re.compile(r'^(?:[0-9a-f]{16})?\s+(?P<type>[AcBbCcDdGgRrSsTtUuVvWw])\s+(?P<symbol>.*)$')
GLIB_REGEX = re.compile(r'@+.*$')


def _file_is_dynamic_library(path: Path):
    with path.open('rb') as f:
        head = f.read(4)
        return head == b'\x7fELF'


def _parse_nm_output(nm_output: str):
    defined_symbols = []
    undefined_symbols = []
    for line in nm_output.splitlines():
        if (match := NM_REGEX.match(line)):
            stype, symbol = match.groups()
            # we just ignore versioned symbols (e.g. func@@GLIB)
            symbol = GLIB_REGEX.sub('', symbol)
            # (T)text, (R)read-only, (W)weak, (B)bss area
            if stype in ['T', 'R', 'W', 'B']:
                defined_symbols.append(symbol)
            elif stype == 'U':  # (U)undefined
                undefined_symbols.append(symbol)
    undefined_symbols = [us for us in undefined_symbols if us not in defined_symbols]
    return defined_symbols, undefined_symbols


def _parse_link_script(path: Path):
    """
    Parses a linker script, that can be used at build time instead of a real library (.so)
    """
    logger.info('Parsing script %s', path)
    libs: list[str] = []
    with path.open() as f:
        lines = f.readlines()
    in_comment = False
    for line in lines:
        if '/*' in line:
            line = re.sub(r'/\*.*$', '', line)
            in_comment = True
        elif in_comment:
            in_comment = not '*/' in line
            line = re.sub(r'^.*(\*/)?', '', line)
        
        # remove AS_NEEDED libs for now
        line = re.sub(r'AS_NEEDED\s*\([^)]*\)', '', line)
        if (match := re.match(r'(GROUP|INPUT)\s*\(([^)]*)\)', line)):
            libs.extend(match.group(2).split())
    logger.debug('script %s links libraries %s', path, ','.join(libs))
    return libs


def _update_cache(cache: Cache, libname: str, defined: list[str], undefined: list[str], *, package=None, system=False):
    cache.add_library(libname, package=package, system=system)

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


def analyze_library_symbols(library_path: Path, dynamic: bool):
    if dynamic:
        cmd = ['nm', '-C', '-D', str(library_path)]
    else:
        cmd = ['nm', '-C', str(library_path)]   
    cp = subprocess.run(cmd, capture_output=True, text=True)
    return _parse_nm_output(cp.stdout)   


def _search_symbols_in_library(path: Path):
    suffix = path.suffixes[0] if len(path.suffixes) > 0 else ''
    if suffix == '.a':
        cmd = ['nm', '-C', str(path)]
    elif suffix == '.so':
        cmd = ['nm', '-C', '-D', str(path)]
    else:
        raise Exception(f'Invalid library path {path}')

    cp = subprocess.run(cmd, capture_output=True, text=True)
    return _parse_nm_output(cp.stdout)   


def analyze_library(library_path: Path, cache: Cache, *, package=None, system=False):
    suffix = library_path.suffixes[0] if len(library_path.suffixes) > 0 else ''
    if suffix == '.so' and not _file_is_dynamic_library(library_path):
        defined, undefined = [], []
        libs = _parse_link_script(library_path)
        for lib in libs:
            lib_def, lib_need = _search_symbols_in_library(Path(lib))
            defined.extend(lib_def)
            undefined.extend(lib_need)
    else:
        defined, undefined = _search_symbols_in_library(library_path)
    
    libname = library_path.name
    _update_cache(cache, libname, defined, undefined, package=package, system=system)

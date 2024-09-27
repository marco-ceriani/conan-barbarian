"""
Data strctures to keep information about libraries, the symbols they define and their dependencies.
"""

from collections.abc import Collection
from pathlib import PurePath, Path
import json
from typing import Optional

class Library:
    __slots__ = ("name", "filename", "system", "package", "_dependencies")

    name: str
    filename: str
    system: bool
    _dependencies: set[str]
    package: str

    def __init__(self, filename, system=False):
        self.name = strip_library_name(filename)
        self.filename = filename
        self.system = system
        self._dependencies = set()

    @property
    def dependencies(self):
        return frozenset(self._dependencies)
    
    def add_dependency(self, dependency: str):
        self._dependencies.add(dependency)

    @staticmethod
    def from_json(data):
        lib = Library(data['file'], data['system'])
        for dependency in data.get('needs', []):
            lib.add_dependency(dependency)
        return lib
    
    def to_json(self):
        return {
            'file': self.filename,
            'system': self.system,
            "needs": self._dependencies
        }

    def __repr__(self):
        return f'Lib({self.name}={self.filename})'

    def __str__(self):
        return self.name
    
    def __eq__(self, value: object) -> bool:
        if isinstance(value, Library):
            return self.filename == value.filename
        return False
    

class Cache:
    _filepath: Optional[Path]
    _libraries: dict[str, Library]
    _defined_symbols: dict[str, str]
    _undefined_symbols: dict[str, set[str]]
    _packages: dict[str, set[str]]
    _components: dict[str, set[str]]
    _libs2components: dict[str, str]

    def __init__(self, path: Optional[Path] = None):
        self._filepath = path
        self._libraries = {}
        self._defined_symbols = {}
        self._undefined_symbols = {}
        self._packages = {}
        self._components = {}
        self._libs2components = {}

    def list_libraries(self):
        return self._libraries.values()

    def all_library_files(self):
        return [lib.filename for lib in self._libraries.values()]

    def is_library(self, library: str):
        return strip_library_name(library) in self._libraries
    
    def get_library(self, library: str):
        lib_name = strip_library_name(library)
        lib = self._libraries.get(lib_name)
        if lib and _different_extension(library, lib.filename):
            return None
        return lib
    
    def find_library(self, libname: str):
        lib = self.get_library(libname)
        return lib and lib.filename

    def add_library(self, library: str, *, system=False, package=None):
        lib = Library(library, system=system)
        self._libraries[lib.name] = lib
        if package:
            self._packages.setdefault(package, set()).add(lib.name)

    def remove_library(self, library: str):
        lib = self._libraries.pop(strip_library_name(library), None)
        if not lib:
            return
        self._defined_symbols = {key:val for key, val in self._defined_symbols.items() if val != lib.filename}

        unneeded_symbols = []
        for key, val in self._undefined_symbols.items():
            try:
                val.remove(lib.filename)
                if len(val) == 0:
                    unneeded_symbols.append(key)
            except KeyError:
                pass
        for symbol in unneeded_symbols:
            del self._undefined_symbols[symbol]

    def add_dependency(self, src, tgt):
        src_name = strip_library_name(src)
        if src != tgt:
            self._libraries[src_name].add_dependency(tgt)

    def get_dependencies(self, library: str, *, transitive=False):
        lib = self.get_library(library)
        if not lib:
            raise Exception(f'{library} is not a library')
        lib_deps = set(lib.dependencies)
        if transitive:
            queue = list(lib_deps)
            while len(queue) > 0:
                item = queue.pop()
                lib_deps.add(item)
                item_lib = self.get_library(item)
                if item_lib:
                    item_deps = item_lib.dependencies
                    new_deps = item_deps - lib_deps
                    queue.extend(new_deps)
        return lib_deps
    
    # Symbols

    @property
    def defined_symbols(self):
        return frozenset(self._defined_symbols.keys())
    
    @property
    def undefined_symbols(self):
        return frozenset(self._undefined_symbols.keys())
    
    def define_symbol(self, symbol: str, library_file: str):
        """Adds the definition of a symbol, and returns a set of libraries that need that symbol"""
        assert self.get_library(library_file)
        self._defined_symbols[symbol] = library_file
        results = self._undefined_symbols.pop(symbol, set())
        return results

    def get_library_defining_symbol(self, symbol: str):
        """Returns the filename of the library that defines a symbol"""
        return self._defined_symbols.get(symbol)
    
    def add_undefined_symbol_dependency(self, symbol, library_file):
        self._undefined_symbols.setdefault(symbol, set()).add(library_file)

    def libraries_needing_undefined_symbol(self, symbol):
        return frozenset(self._undefined_symbols.get(symbol, []))

    def is_package(self, package: str):
        return package in self._packages
    
    def package_libraries(self, package):
        return list(self._packages.get(package, []))
    
    # components

    def is_component(self, component: str):
        return component in self._components

    def get_component_libraries(self, component: str):
        return self._components.get(component, set())
    
    def set_component_libraries(self, component: str, libraries: list[str]):
        self._components[component] = set(libraries)

    def get_library_component(self, lib: str):
        if len(self._components) > 0 and len(self._libs2components) == 0:
            self.__build_components_reverse_map()

        return self._libs2components.get(strip_library_name(lib), None)

    def __build_components_reverse_map(self):
        for comp, libs in self._components.items():
            for lib in libs:
                self._libs2components[strip_library_name(lib)] = comp

    def filter_system_libraries(self, libs: Collection[str], system: bool):
        def is_system_library(name):
            lib = self.get_library(name)
            return lib is not None and lib.system
        return [name for name in libs if is_system_library(name) == system]


    def to_json(self):
        return {
            'libraries': list(self._libraries.values()),
            'defined': self._defined_symbols,
            'undefined': self._undefined_symbols,
            'packages': self._packages,
            'components': self._components,
        }

    def load(self):
        try:
            with open(self._filepath, 'r') as f:
                data = json.load(f)
                libraries = [Library.from_json(lib) for lib in data['libraries']]
                self._libraries = {lib.name: lib for lib in libraries}
                self._packages = {k: set(v) for k, v in data['packages'].items()}
                self._defined_symbols = data['defined']
                self._undefined_symbols = {k: set(v) for k, v in data['undefined'].items()}
                self._components = {k: set(v) for k, v in data['components'].items()}
        except FileNotFoundError:
            pass

    def save(self):
            if not self._filepath:
                raise('cannot save cache: file path not set')
            with open(self._filepath, 'w') as f:
                json.dump(self, f, indent=2, default=json_encoder)


def strip_library_name(name):
    return PurePath(name).stem.removeprefix('lib')


def _different_extension(first, second):
    ext1 = PurePath(first).suffix
    ext2 = PurePath(second).suffix
    return ext1 and ext1 != ext2


def json_encoder(obj):
    if getattr(obj.__class__, 'to_json', None):
        return obj.to_json()
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f'unexpected {obj}')

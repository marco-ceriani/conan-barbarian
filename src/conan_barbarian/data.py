from collections.abc import Collection
from pathlib import PurePath, Path
import json
from typing import Optional

class Library:
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
    filepath: Optional[Path]
    libraries: dict[str, Library]
    dependencies: dict[str, set[str]]
    defined_symbols: dict[str, str]
    undefined_symbols: dict[str, set[str]]
    packages: dict[str, set[str]]
    components: dict[str, set[str]]
    _libs2components: dict[str, str]

    def __init__(self, path: Optional[Path] = None):
        self.filepath = path
        self.libraries = {}
        self.defined_symbols = {}
        self.undefined_symbols = {}
        self.packages = {}
        self.components = {}
        self._libs2components = {}

    def list_libraries(self):
        return self.libraries.values()

    def all_library_files(self):
        return [lib.filename for lib in self.libraries.values()]

    def is_library(self, library: str):
        return strip_library_name(library) in self.libraries
    
    def get_library(self, library: str):
        lib_name = strip_library_name(library)
        lib = self.libraries.get(lib_name)
        if lib and _different_extension(library, lib.filename):
            return None
        return lib
    
    def find_library(self, libname: str):
        lib = self.get_library(libname)
        return lib and lib.filename

    def add_library(self, library: str, *, system=False, package=None):
        lib = Library(library, system=system)
        self.libraries[lib.name] = lib
        if package:
            self.packages.setdefault(package, set()).add(lib.name)

    def add_dependency(self, src, tgt):
        src_name = strip_library_name(src)
        if src != tgt:
            self.libraries[src_name].add_dependency(tgt)

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
    
    def define_symbol(self, symbol: str, library_file: str):
        """Adds the definition of a symbol, and returns a set of libraries that need that symbol"""
        assert self.get_library(library_file)
        self.defined_symbols[symbol] = library_file
        results = self.undefined_symbols.pop(symbol, set())
        return results

    def get_library_defining_symbol(self, symbol: str):
        """Returns the filename of the library that defines a symbol"""
        return self.defined_symbols.get(symbol)
    
    def add_undefined_symbol_dependency(self, symbol, library_file):
        self.undefined_symbols.setdefault(symbol, set()).add(library_file)

    def is_package(self, package: str):
        return package in self.packages
    
    def package_libraries(self, package):
        return list(self.packages.get(package, []))
    
    # components

    def is_component(self, component: str):
        return component in self.components

    def get_component_libraries(self, component: str):
        return self.components.get(component, set())
    
    def set_component_libraries(self, component: str, libraries: list[str]):
        self.components[component] = set(libraries)

    def get_library_component(self, lib: str):
        if len(self.components) > 0 and len(self._libs2components) == 0:
            self.__build_components_reverse_map()

        return self._libs2components.get(strip_library_name(lib), None)

    def __build_components_reverse_map(self):
        for comp, libs in self.components.items():
            for lib in libs:
                self._libs2components[strip_library_name(lib)] = comp

    def filter_system_libraries(self, libs: Collection[str], system: bool):
        return [name for name in libs if (lib := self.get_library(name)) and lib.system == system]


    def to_json(self):
        return {
            'libraries': list(self.libraries.values()),
            'defined': self.defined_symbols,
            'undefined': self.undefined_symbols,
            'packages': self.packages,
            'components': self.components,
        }

    def load(self):
        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)
                libraries = [Library.from_json(lib) for lib in data['libraries']]
                self.libraries = {lib.name: lib for lib in libraries}
                self.packages = {k: set(v) for k, v in data['packages'].items()}
                self.defined_symbols = data['defined']
                self.undefined_symbols = {k: set(v) for k, v in data['undefined'].items()}
                self.components = {k: set(v) for k, v in data['components'].items()}
        except FileNotFoundError:
            pass

    def save(self):
            if not self.filepath:
                raise('cannot save cache: file path not set')
            with open(self.filepath, 'w') as f:
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

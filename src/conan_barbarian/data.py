from pathlib import PurePath, Path
import json

class Library:
    name: str
    filename: str
    system: bool
    _dependencies: set[str]

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

    def __repr__(self):
        return f'Lib({self.name}={self.filename})'

    def __str__(self):
        return self.name
    

class Cache:
    filepath: Path
    dependencies: dict[str, set[str]]
    defined_symbols: dict[str, str]
    undefined_symbols: dict[str, set[str]]
    components: dict[str, list[str]]
    libraries: dict[str, Library]

    def __init__(self, path: Path = None):
        self.filepath = path
        self.defined_symbols = {}
        self.undefined_symbols = {}
        self.components = {}
        self.libraries = {}

    def list_libraries(self):
        return self.libraries.values()

    def all_library_files(self):
        return [lib.filename for lib in self.libraries.values()]

    def is_library(self, library: str):
        return library in self.libraries
    
    def get_library(self, library: str):
        lib_name = strip_library_name(library)
        return self.libraries.get(lib_name)
    
    def find_library(self, libname: str):
        name = strip_library_name(libname)
        lib = self.libraries.get(name)

        if lib is None:
            return None

        ext = PurePath(libname).suffix
        if ext and PurePath(lib.filename).suffix != ext:
            return None
        return lib.filename

    def add_library(self, library: str, *, system=False):
        lib = Library(library, system=system)
        self.libraries[lib.name] = lib

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
        return self.undefined_symbols.pop(symbol, set())

    def get_library_defining_symbol(self, symbol: str):
        """Returns the filename of the library that defines a symbol"""
        return self.defined_symbols.get(symbol)
    
    def add_undefined_symbol_dependency(self, symbol, library_file):
        self.undefined_symbols.setdefault(symbol, set()).add(library_file)

    def is_component(self, component: str):
        return component in self.components

    def get_component_libraries(self, component: str):
        return self.components.get(component, [])
    
    def set_component_libraries(self, component: str, libraries: list[str]):
        self.components[component] = set(libraries)

    def load(self):
        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)
                libraries = [Library(lib['file'], lib['system']) for lib in data['libraries']]
                self.libraries = {lib.name: lib for lib in libraries}
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


def json_encoder(obj):
    if isinstance(obj, Cache):
        return {
            'libraries': list(obj.libraries.values()),
            'defined': obj.defined_symbols,
            'undefined': obj.undefined_symbols,
            'components': obj.components,
        }
    if isinstance(obj, Library):
        return {
            'name': obj.name,
            'file': obj.filename,
            'system': obj.system
        }
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f'unexpected {obj}')

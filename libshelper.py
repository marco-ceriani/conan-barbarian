#!/usr/bin/env python3

import sys
from pathlib import Path, PurePath
import subprocess
import re
import json
import argparse
import logging
import pdb

logger = logging.getLogger(__name__)


###############################################################################
#  Data Cache
###############################################################################


def json_encoder(obj):
    if isinstance(obj, Cache):
        return {
            'defined': obj.defined_symbols,
            'undefined': obj.undefined_symbols,
            'dependencies': obj.dependencies,
        }
    if isinstance(obj, set):
        return list(obj)
    raise TypeError


CACHE_NAME = '.libscache'


class Cache:
    __slots__ = ("defined_symbols", "undefined_symbols", "dependencies")

    dependencies: dict[str, set[str]]
    defined_symbols: dict[str, str]
    undefined_symbols: dict[str, set[str]]

    def __init__(self):
        self.defined_symbols = {}
        self.undefined_symbols = {}
        self.dependencies = {}
        self.load()
    
    def is_library(self, library: str):
        return library in self.dependencies
    
    def find_library(self, name: str):
        if not name.startswith('lib'):
            name = 'lib' + name

        suffix = PurePath(name).suffix
        candidates = [name] if suffix else [f'{name}.a', f'{name}.so']
        for candidate in candidates:
            if self.is_library(candidate):
                return candidate
        return None
    
    def add_library(self, library: str):
        self.dependencies.setdefault(library, set())

    def add_dependency(self, src, tgt):
        if src != tgt:
            self.dependencies.setdefault(src, set()).add(tgt)

    def get_dependencies(self, library: str, transitive=False):
        deps = self.dependencies.get(library, set())
        if transitive:
            queue = list(deps)
            while len(queue) > 0:
                item = queue.pop()
                item_deps = self.dependencies.get(item, set())
                new_deps = item_deps - deps
                queue.extend(new_deps)
        return deps


    def load(self):
        try:
            with open(CACHE_NAME, 'r') as f:
                data = json.load(f)
                self.defined_symbols = data['defined']
                self.undefined_symbols = {k: set(v) for k, v in data['undefined'].items()}
                self.dependencies = {k: set(v) for k, v in data['dependencies'].items()}
        except FileNotFoundError:
            pass

    def save(self):
            with open(CACHE_NAME, 'w') as f:
                json.dump(self, f, indent=2, default=json_encoder)


###############################################################################
#  Libraries Analisys
###############################################################################


def parse_nm_output(nm_output):
    defined_symbols = []
    undefined_symbols = []
    for line in nm_output.splitlines():
        if (match := re.match(r'^(?:[0-9a-f]{16})?\s+(?P<type>[AcBbCcDdGgRrSsTtUuVvWw])\s+(?P<symbol>.*)$', line)):
            stype, symbol = match.groups()
            # (T)ext, (R)ead-only, (W)eak
            if stype in ['T', 'R', 'W']:
                defined_symbols.append(symbol)
            elif stype == 'U':  # (U)ndefined
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
    defined, undefined = parse_nm_output(cp.stdout)

    cache.add_library(libname)

    for symbol in defined:
        cache.defined_symbols[symbol] = libname
        depending_libs = cache.undefined_symbols.pop(symbol, None)
        if depending_libs:
            for dl in depending_libs:
                cache.add_dependency(dl, libname)

    for symbol in undefined:
        definer = cache.defined_symbols.get(symbol, None)
        if definer:
            cache.add_dependency(libname, definer)
        else:
            cache.undefined_symbols.setdefault(symbol, set()).add(libname)


class DepGraphNode:
    def __init__(self, name: str):
        self.name = name
        self.in_refs = set()
        self.out_refs = set()
        self.data = {}

    @property
    def is_root(self):
        return len(self.in_refs) == 0

    def __repr__(self):
        return f"Node({self.name}, depends_on:{[n.name for n in self.out_refs]})"


class DepGraph:
    def __init__(self):
        self.nodes: dict[str, DepGraphNode] = {}

    def get_keys(self) -> list[str]:
        return self.nodes.keys()
    
    def get_nodes(self) -> list[DepGraphNode]:
        return list(self.nodes.values())
    
    def get_node(self, lib: str):
        node = self.nodes.get(lib, None)
        if not node:
            node = DepGraphNode(lib)
            self.nodes[lib] = node
        return node
    
    def add_dependency(self, src: str, tgt: str):
        src_node = self.get_node(src)
        tgt_node = self.get_node(tgt)
        src_node.out_refs.add(tgt_node)
        tgt_node.in_refs.add(src_node)

    def remove_dependency(self, src: str, tgt: str):
        src_node = self.get_node(src)
        tgt_node = self.get_node(tgt)
        src_node.out_refs.remove(tgt_node)
        tgt_node.in_refs.remove(src_node)

    def create(self, cache: Cache, roots: list[str]):
        if not roots:
            roots = cache.dependencies.keys()
        for lib in roots:
            self.get_node(lib)
            node_deps = cache.dependencies.get(lib, [])
            for dep in node_deps:
                if dep != lib:
                    self.add_dependency(lib, dep)

    def __repr__(self):
        return f"DepGraph[{str(list(self.nodes.values()))}]"


def compute_dependencies(cache: Cache, libs: list[str]):
    logger = logging.getLogger('graph')

    graph = DepGraph()
    graph.create(cache, libs)

    for i, lib in enumerate(libs):
        graph.get_node(lib).data['order'] = i

    roots = [n for n in graph.get_nodes() if n.is_root]
    roots.sort(key = lambda n : n.data.get('order', 10_000))
    sorted_libs = []

    while len(roots) > 0:
        node = roots.pop()
        sorted_libs.append(node.name)
        logger.debug(f'processing node {node}')
        node_dependencies: set[DepGraphNode] = node.out_refs.copy()
        for target in node_dependencies:
            graph.remove_dependency(node.name, target.name)
            if target.is_root:
                roots.append(target)
    return sorted_libs


def find_lib_with_name(cache: Cache, name: str):
    lib_name = name if name.startswith('lib') else 'lib' + name

    suffix = PurePath(lib_name).suffix
    if suffix:
        candidates = [lib_name]
    else:
        candidates = [f'{lib_name}.a', f'{lib_name}.so']
    for candidate in candidates:
        if cache.is_library(candidate):
            return candidate
    return name


def quote_lib_name(name: str, args: argparse.Namespace):
    if args.quote:
        return args.quote + name + args.quote
    return name

def format_lib(name: str, args: argparse.Namespace):
    if isinstance(name, (list, set)):
        return [format_lib(x, args) for x in name]
    
    mode = args.names
    if mode == 'short':
        name = PurePath(name).stem.removeprefix('lib')
    return quote_lib_name(name, args)


def minimize_dependencies_list(cache: Cache, libs: list[str]):
    result = libs.copy()
    for lib in libs:
        deps = cache.get_dependencies(lib)
        for d in deps:
            try:
                result.remove(d)
            except KeyError:
                pass
    return result


###############################################################################
#  CLI Commands
###############################################################################


def cmd_analyze_libs(cache: Cache, args: argparse.Namespace):

    def check_and_analyze(lib: Path, cache: Cache, args: argparse.Namespace):
        lib_name = lib.name
        if args.force or not cache.is_library(lib_name):
            print(f'analyzing {lib}')
            analyze_library(lib, cache)

    for lib in args.libs:
        path = Path(lib)
        if path.is_file():
            check_and_analyze(path, cache, args)
        elif path.is_dir():
            for child in path.glob(r'**/*'):
                if child.suffix in ['.a', '.so']:
                    check_and_analyze(child, cache, args)
    cache.save()


def cmd_sort_libs(cache: Cache, args: argparse.Namespace):
    patched_names = [lib_name for lib in args.libs if (lib_name := cache.find_library(lib))]
    order = compute_dependencies(cache, patched_names)
    order = format_lib(order, args)

    list_separator = bytes(args.sep, 'utf-8').decode('unicode_escape')
    print('Libraries sorted according to dependencies: \n' + list_separator.join(order))


def cmd_find_symbol(cache: Cache, args: argparse.Namespace):
    lib = cache.defined_symbols.get(args.symbol, None)
    if not lib:
        print(f"Symbol {args.symbol} not found")
        sys.exit(-1)
    print(f"Symbol {args.symbol} found in library {format_lib(lib, args)}")


def cmd_find_dependencies(cache: Cache, args: argparse.Namespace):
    print("Libraries dependencies:")
    for lib in args.libs:
        lib_name = cache.find_library(lib)
        if not lib_name:
            print(f"- {lib}: <not found>")
            continue

        deps = cache.get_dependencies(lib_name)
        if args.minimize:
            deps = minimize_dependencies_list(cache, deps)
        elif args.recursive:
            deps = compute_dependencies(cache, deps)
        if args.sort:
            deps = sorted(deps)

        if len(deps) == 0:
            print(f"- {lib}: <none>")
        else:
            print(f"- {lib}: " + ", ".join(format_lib(deps, args)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title='commands', required=True)

    print_args = argparse.ArgumentParser(add_help=False)
    print_args.add_argument('-v', '--verbose', action='store_true')
    print_args.add_argument('--names', choices=['short', 'full'], default="short")
    print_args.add_argument('--quote', default='')

    parser_analyze = subparsers.add_parser('analyze', parents=[print_args],
                                            help='analyzes a list of libraries')
    parser_analyze.add_argument('libs', nargs='+', help='paths to libraries or folders')
    parser_analyze.add_argument('-f', '--force', help='force analysis replacing cached info', action='store_true')  # just overwrites, not replaces
    parser_analyze.set_defaults(func=cmd_analyze_libs)

    parser_sort = subparsers.add_parser('sort', parents=[print_args],
                                         help='sort a list of libraries according to dependency relations') 
    parser_sort.add_argument('libs', nargs='+')
    parser_sort.add_argument('--sep', default=', ', help='list separator')
    parser_sort.set_defaults(func=cmd_sort_libs)

    parser_find = subparsers.add_parser('find', parents=[print_args],
                                         help='finds a symbol in the libraries') 
    parser_find.add_argument('symbol')
    parser_find.set_defaults(func=cmd_find_symbol)

    parser_deps = subparsers.add_parser('dependencies', parents=[print_args],
                                         help='list the dependencies of one or more libraries') 
    parser_deps.add_argument('libs', nargs='+')
    parser_deps.add_argument('--minimize', action='store_true')
    parser_deps.add_argument('-r', '--recursive', action='store_true')
    parser_deps.add_argument('--sort', action='store_true', help='sort lexicographically')
    parser_deps.set_defaults(func=cmd_find_dependencies)

    args = parser.parse_args()

    logging.basicConfig(
        format='%(message)s',
        level=logging.DEBUG if args.verbose else logging.WARN
    )

    cache = Cache()
    args.func(cache, args)

    sys.exit(0)

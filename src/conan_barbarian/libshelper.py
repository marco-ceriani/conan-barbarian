#!/usr/bin/env python3

import sys
from pathlib import Path, PurePath
import subprocess
import re
import argparse
import logging
import fnmatch
from conan_barbarian.data import Cache

logger = logging.getLogger(__name__)


###############################################################################
#  Libraries Analisys
###############################################################################


def parse_nm_output(nm_output):
    defined_symbols = []
    undefined_symbols = []
    for line in nm_output.splitlines():
        if (match := re.match(r'^(?:[0-9a-f]{16})?\s+(?P<type>[AcBbCcDdGgRrSsTtUuVvWw])\s+(?P<symbol>.*)$', line)):
            stype, symbol = match.groups()
            # (T)text, (R)read-only, (W)weak, (B)bss area
            if stype in ['T', 'R', 'W', 'B']:
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


class DepGraphNode:
    __slots__ = ("name", "in_refs", "out_refs", "data")

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

    def __str__(self):
        return self.name


class DepGraph:
    __slots__ = ("nodes")

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
        for lib in roots:
            self.get_node(lib)
            node_deps = cache.get_dependencies(lib)
            for dep in node_deps:
                if dep != lib:
                    self.add_dependency(lib, dep)

    def __repr__(self):
        return f"DepGraph[{str(list(self.nodes.values()))}]"


def sort_by_dependency(cache: Cache, libs: list[str]):
    logger = logging.getLogger('graph')

    graph = DepGraph()
    graph.create(cache, libs)

    roots = [n for n in graph.get_nodes() if n.is_root]
    sorted_libs = []

    while len(roots) > 0:
        roots.sort(key=lambda n : n.name)
        sorted_libs.extend([r.name for r in roots])
        next_roots = []
        for node in roots:
            logger.debug('processing node %s', node)
            node_dependencies: set[DepGraphNode] = node.out_refs.copy()
            for target in node_dependencies:
                graph.remove_dependency(node.name, target.name)
                if target.is_root:
                    next_roots.append(target)
        roots = next_roots
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

def strip_library_name(name):
    return PurePath(name).stem.removeprefix('lib')

def format_lib(name: str, args: argparse.Namespace):
    if isinstance(name, (list, set)):
        return [format_lib(x, args) for x in name]
    
    mode = args.names
    if mode == 'short':
        name = strip_library_name(name)
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
    order = sort_by_dependency(cache, patched_names)
    order = format_lib(order, args)

    list_separator = bytes(args.sep, 'utf-8').decode('unicode_escape')
    print('Libraries sorted according to dependencies: \n' + list_separator.join(order))


def cmd_find_symbol(cache: Cache, args: argparse.Namespace):
    lib = cache.get_library_defining_symbol(args.symbol)
    if not lib:
        print(f"Symbol '{args.symbol}' not found")
        sys.exit(-1)
    print(f"Symbol '{args.symbol}' found in library {format_lib(lib, args)}")


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
            deps = sort_by_dependency(cache, deps)
        if args.sort:
            deps = sorted(deps)

        if len(deps) == 0:
            print(f"- {lib}: <none>")
        else:
            print(f"- {lib}: " + ", ".join(format_lib(deps, args)))


def cmd_print_cpp_info(cache: Cache, args: argparse.Namespace):
    print('Conan style cpp_info:\n')
    for lib in args.libs:
        if cache.is_component(lib):
            libs = cache.get_component_libraries(lib)
        else:
            libs = [lib]
        lib_name = cache.find_library(lib)
        used_libraries = cache.get_dependencies(lib_name)
        if args.minimize:
            used_libraries = minimize_dependencies_list(cache, used_libraries)
        dependencies = [strip_library_name(lib) for lib in used_libraries]

        lib_names = ', '.join([f'"{strip_library_name(l)}"' for l in libs])
        print(f'self.cpp_info.components["{lib}"].libs = [{lib_names}]')
        print(f'self.cpp_info.components["{lib}"].requires.extend([')
        for dep in dependencies:
            print(f'    "{dep}"')
        print('])')


def cmd_define_component(cache: Cache, args: argparse.Namespace):
    component = args.component
    current_libraries = cache.get_component_libraries(component)
    logger.debug('old libraries in component %s: %s', component, current_libraries)

    libs = []
    all_libs = cache.all_library_files(skip_empty=True)
    for lib in args.libs:
        new_libs = fnmatch.filter(all_libs, lib)
        libs.extend(new_libs)
    cache.set_component_libraries(component, libs)

    cache.save()


def configure_logging(args: argparse.Namespace):
    level = logging.WARN
    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG

    logging.basicConfig(
        format='%(levelname)s: %(message)s',
        level=level
    )


def main_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', help='project_file')
    subparsers = parser.add_subparsers(title='commands', required=True)

    print_args = argparse.ArgumentParser(add_help=False)
    print_args.add_argument('-v', '--verbose', action='count', default=0)
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

    module = subparsers.add_parser('component', parents=[print_args]) 
    module.add_argument('component', help='the component name')
    module.add_argument('libs', nargs='+', help='library names or globs')
    module.set_defaults(func=cmd_define_component)

    cpp_info = subparsers.add_parser('cppinfo', parents=[print_args])
    cpp_info.add_argument('libs', nargs='+')
    cpp_info.add_argument('--minimize', action='store_true')
    cpp_info.set_defaults(func=cmd_print_cpp_info)

    args = parser.parse_args()

    configure_logging(args)

    cache = Cache(Path(args.project))
    cache.load()
    args.func(cache, args)

    sys.exit(0)

if __name__ == '__main__':
    main_cli()

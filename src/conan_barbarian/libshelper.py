#!/usr/bin/env python3

from os import replace
import re
import sys
from pathlib import Path, PurePath
import argparse
import logging
import fnmatch
from collections.abc import Collection

from conan_barbarian.data import Cache
from conan_barbarian.graphs import DepGraph, DepGraphNode, prune_arcs, sort_graph
from conan_barbarian.scraping import analyze_library

logger = logging.getLogger(__name__)


def filter_libraries(cache: Cache, libs: list[str]):
    patched_names = []
    for lib in libs:
        lib_name = cache.find_library(lib)
        if lib_name:
            patched_names.append(lib_name)
        else:
            logger.warning("library '%s' not defined", lib)
    return patched_names


def create_libs_graph(cache: Cache, roots: list[str]):
    """
    Creates a graph with the input libraries and all their dependencies.
    """
    graph = DepGraph()
    visited = set()
    queue = list(roots)
    while len(queue) > 0:
        item = queue.pop()
        if not cache.is_library(item):
            raise Exception(f"'{item} is not a library")

        graph.get_node(item)
        visited.add(item)
        item_deps = cache.get_dependencies(item)
        for dep in item_deps:
            graph.add_dependency(item, dep)
            if not dep in queue and not dep in visited:
                queue.append(dep)
    return graph


def replace_libs_with_components(cache: Cache, graph: DepGraph):
    for node in graph.nodes:
        component = cache.get_library_component(node.name)
        if component:
            logger.debug(f"replacing '{node.name}' with '{component}'")
            comp_node = graph.get_node(component)
            for src in node.in_refs:
                if src != comp_node:
                    graph.add_dependency(src.name, component)
            for tgt in node.out_refs:
                if tgt != comp_node:
                    graph.add_dependency(component, tgt.name)
            graph.remove_node(node.name)


def sort_by_dependency(cache: Cache, libs: list[str]):
    graph = create_libs_graph(cache, libs)
    return sort_graph(graph)


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
            except ValueError:
                pass
    return result


###############################################################################
#  CLI Commands
###############################################################################


def cmd_analyze_libs(cache: Cache, args: argparse.Namespace):

    def check_and_analyze(lib: Path, cache: Cache, args: argparse.Namespace):
        lib_name = lib.name
        if not cache.is_library(lib_name):
            print(f'analyzing {lib}')
            analyze_library(lib, cache, package=args.package)

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
    patched_names = filter_libraries(cache, args.libs)
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


def print_component_cpp_info(component: str, libs: Collection[str], dependencies: Collection[str], *, indent='\t'):
    lib_names = ', '.join([f'"{strip_library_name(l)}"' for l in libs])
    print(f'{indent}{indent}self.cpp_info.components["{component}"].libs = [{lib_names}]')
    if len(dependencies) > 0:
        print(f'{indent}{indent}self.cpp_info.components["{component}"].requires.extend([')
        for dep in dependencies:
            print(f'{indent}{indent}{indent}"{dep}",')
        print(f'{indent}{indent}])')
    print()


def expand_args_to_libraries(cache: Cache, items: list[str]):
    libraries = set()
    for item in items:
        if cache.is_package(item):
            libraries.update(cache.package_libraries(item))
        elif cache.is_component(item):
            libraries.update(cache.get_component_libraries(item))
        else:
            libraries.add(item)
    return libraries


class ComponentInfo:
    __slots__ = ("libs", "deps")
    libs: set[str]
    deps: set[str]

    def __init__(self, libs=set(), deps=set()):
        self.libs = libs
        self.deps = deps


def cmd_print_cpp_info(cache: Cache, args: argparse.Namespace):
    libraries = expand_args_to_libraries(cache, args.items)
    graph = create_libs_graph(cache, libraries)

    indentation = '\t'
    if args.indent > 0:
        indentation = ''.join([' ' for x in range(args.indent)])

    replace_libs_with_components(cache, graph)
    if args.minimize:
        graph = prune_arcs(graph)

    def patch_lib_name(name):
        stripped = strip_library_name(name)
        if cache.is_package(stripped):
            return f'_{stripped}'
        return stripped

    def node_visitor(node: DepGraphNode):
        if cache.is_component(node.name):
            libs = cache.get_component_libraries(node.name)
            deps = {patch_lib_name(lib_node.name) for lib_node in node.out_refs}
            deps = deps.difference(libs)
            print_component_cpp_info(node.name, libs, deps, indent=indentation)
        else:
            lib = cache.get_library(node.name)
            component_name = patch_lib_name(lib.name)
            deps = {patch_lib_name(out.name) for out in node.out_refs}
            print_component_cpp_info(component_name, [lib.name], deps, indent=indentation)

    print('from conan import ConanFile')
    print('class Template(ConanFile):')
    print('{0}def package_info(self):'.format(indentation))
    graph.traverse(node_visitor)


def cmd_define_component(cache: Cache, args: argparse.Namespace):
    component = args.component
    current_libraries = cache.get_component_libraries(component)
    logger.debug('old libraries in component %s: %s', component, current_libraries)

    libs = []
    all_libs = cache.all_library_files()
    for lib in args.libs:
        new_libs = fnmatch.filter(all_libs, lib)
        libs.extend(new_libs)
    cache.set_component_libraries(component, libs)

    cache.save()


def cmd_print_graph(cache: Cache, args: argparse.Namespace):
    graph = create_libs_graph(cache, args.libs)
    if args.show_components:
        replace_libs_with_components(cache, graph)
    print(graph.to_dot())


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
    parser_analyze.add_argument('--system', action='store_true')
    parser_analyze.add_argument('--package', help='add the libraries to a logical package')
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

    module = subparsers.add_parser('component', parents=[print_args],
                                   help='define a component grouping multiple libraries') 
    module.add_argument('component', help='the component name')
    module.add_argument('libs', nargs='+', help='library names or globs')
    module.set_defaults(func=cmd_define_component)

    graph = subparsers.add_parser('graph', parents=[print_args],
                                   help='print the dependencies graph of a set of libraries') 
    graph.add_argument('libs', nargs='+', help='libraries')
    graph.add_argument('--show-components', action='store_true')
    graph.set_defaults(func=cmd_print_graph)

    cpp_info = subparsers.add_parser('cppinfo', parents=[print_args])
    cpp_info.add_argument('items', nargs='+')
    cpp_info.add_argument('--minimize', action='store_true')
    cpp_info.add_argument('--indent', default=0, type=int)
    cpp_info.set_defaults(func=cmd_print_cpp_info)

    args = parser.parse_args()

    configure_logging(args)

    cache = Cache(Path(args.project))
    cache.load()
    args.func(cache, args)

    sys.exit(0)

if __name__ == '__main__':
    main_cli()

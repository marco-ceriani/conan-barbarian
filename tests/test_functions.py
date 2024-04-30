# tested unit
import pytest
import conan_barbarian.libshelper as ut
from conan_barbarian.data import Cache
from conan_barbarian.graphs import DepGraph


def add_libraries(cache: Cache, libs: list[str]):
    for lib in libs:
        cache.add_library(lib)


def test_filter_libs():
    cache = Cache()
    add_libraries(cache, ['libfoo.so', 'libbar.a', 'libbaz.so'])

    assert ut.filter_libraries(cache, ['libfoo.so']) == ['libfoo.so']
    assert ut.filter_libraries(cache, ['libfoo.so', 'libbar.a']) == ['libfoo.so', 'libbar.a']
    assert ut.filter_libraries(cache, []) == []
    assert ut.filter_libraries(cache, ['libghost.so']) == []
    assert ut.filter_libraries(cache, ['baz', 'bar']) == ['libbaz.so', 'libbar.a']
    assert ut.filter_libraries(cache, ['foo', 'libbar']) == ['libfoo.so', 'libbar.a']


def test_create_graph():
    cache = Cache()
    add_libraries(cache, ['lib1.so', 'lib2.so', 'lib3.so', 'lib4.so', 'lib5.so'])
    cache.add_dependency('lib1.so', 'lib2.so')
    cache.add_dependency('lib1.so', 'lib3.so')
    cache.add_dependency('lib2.so', 'lib4.so')
    cache.add_dependency('lib3.so', 'lib4.so')
    cache.add_dependency('lib2.so', 'lib5.so')

    # single leaf
    graph = ut.create_libs_graph(cache, ['lib5.so'])
    assert graph.get_keys() == {'lib5.so'}

    # one arg with two children
    graph = ut.create_libs_graph(cache, ['lib2.so'])
    assert graph.get_keys() == {'lib2.so', 'lib4.so', 'lib5.so'}

    # two children, one in arguments
    graph = ut.create_libs_graph(cache, ['lib5.so', 'lib2.so'])
    assert graph.get_keys() == {'lib2.so', 'lib4.so', 'lib5.so'}

    # one child
    graph = ut.create_libs_graph(cache, ['lib3.so'])
    assert graph.get_keys() == {'lib3.so', 'lib4.so'}

    # the root
    graph = ut.create_libs_graph(cache, ['lib1.so'])
    assert graph.get_keys() == {'lib1.so', 'lib2.so', 'lib3.so', 'lib4.so', 'lib5.so'}

    # the root and some other node in arguments
    graph = ut.create_libs_graph(cache, ['lib5.so', 'lib3.so', 'lib1.so'])
    assert graph.get_keys() == {'lib1.so', 'lib2.so', 'lib3.so', 'lib4.so', 'lib5.so'}


def node_children(graph: DepGraph, id: str):
    return {n.name for n in graph.get_node(id).out_refs}


def test_create_graph_with_components():
    cache = Cache()
    add_libraries(cache, [f'lib{i}.so' for i in range(1, 7)])
    cache.add_dependency('lib1.so', 'lib2.so')
    cache.add_dependency('lib1.so', 'lib3.so')
    cache.add_dependency('lib1.so', 'lib4.so')
    cache.add_dependency('lib3.so', 'lib5.so')
    cache.add_dependency('lib4.so', 'lib6.so')
    cache.set_component_libraries('comp', ['lib3.so', 'lib4.so'])

    graph = ut.create_libs_graph(cache, ['lib1.so', 'comp'])
    print(graph.to_dot())

    assert 'comp' in graph.get_keys()

    assert node_children(graph, 'comp') == {'lib3.so', 'lib4.so'}
    
    lib1_targets = {n.name for n in graph.get_node('lib1.so').out_refs}
    assert lib1_targets == {'lib2.so', 'comp'}

    lib2_targets = {n.name for n in graph.get_node('lib2.so').out_refs}
    assert lib2_targets == set()


def test_create_graph_with_more_components():
    cache = Cache()
    add_libraries(cache, [f'lib{i}.so' for i in range(1, 9)])
    cache.add_dependency('lib1.so', 'lib2.so')
    cache.add_dependency('lib1.so', 'lib3.so')
    cache.add_dependency('lib1.so', 'lib4.so')
    cache.add_dependency('lib3.so', 'lib5.so')
    cache.add_dependency('lib3.so', 'lib6.so')
    cache.add_dependency('lib4.so', 'lib6.so')
    cache.add_dependency('lib4.so', 'lib7.so')
    cache.add_dependency('lib5.so', 'lib8.so')
    cache.set_component_libraries('comp34', ['lib3.so', 'lib4.so'])
    cache.set_component_libraries('comp56', ['lib5.so', 'lib6.so'])
    cache.set_component_libraries('comp7', ['lib7.so'])

    graph = ut.create_libs_graph(cache, ['comp34', 'lib1.so', 'comp56'])
    print(graph.to_dot())

    comp34_targets = {n.name for n in graph.get_node('comp34').out_refs}
    assert comp34_targets == {'lib3.so', 'lib4.so'}

    comp56_targets = {n.name for n in graph.get_node('comp56').out_refs}
    assert comp56_targets == {'lib5.so', 'lib6.so'}

    lib3_targets = {n.name for n in graph.get_node('lib3.so').out_refs}
    assert lib3_targets == {'comp56'}

    lib4_targets = {n.name for n in graph.get_node('lib4.so').out_refs}
    assert lib4_targets == {'comp56', 'comp7'}


@pytest.mark.timeout(5)
def test_create_graph_with_components_with_internal_dependencies():
    cache = Cache()
    add_libraries(cache, [f'lib{i}.so' for i in range(1, 7)])
    cache.add_dependency('lib1.so', 'lib2.so')
    cache.add_dependency('lib1.so', 'lib3.so')
    cache.add_dependency('lib1.so', 'lib4.so')
    cache.add_dependency('lib2.so', 'lib5.so')
    cache.add_dependency('lib4.so', 'lib5.so')
    cache.add_dependency('lib5.so', 'lib6.so')
    cache.set_component_libraries('compx', ['lib2.so', 'lib3.so', 'lib5.so'])

    graph = ut.create_libs_graph(cache, ['lib1.so'])
    print(graph.to_dot())

    assert node_children(graph, 'lib1.so') == {'compx', 'lib4.so'}
    assert node_children(graph, 'lib4.so') == {'compx'}
    assert node_children(graph, 'compx') == {'lib2.so', 'lib3.so', 'lib5.so'}
    assert node_children(graph, 'lib3.so') == set()
    assert node_children(graph, 'lib5.so') == {'lib6.so'}
    assert node_children(graph, 'lib6.so') == set()
    assert node_children(graph, 'lib2.so') == {'lib5.so'}


def test_sort_libraries():
    cache = Cache()
    add_libraries(cache, ['libcat.so', 'libdog.a', 'libbird.so'])
    cache.add_dependency('dog', 'cat')
    cache.add_dependency('cat', 'bird')

    res = ut.sort_by_dependency(cache, ['bird', 'cat', 'dog'])
    assert res == ['dog', 'cat', 'bird']

    assert ut.sort_by_dependency(cache, ['bird', 'dog']) == ['dog', 'cat', 'bird']

    assert ut.sort_by_dependency(cache, ['bird', 'cat']) == ['cat', 'bird']


def test_minimize_deps_list():
    cache = Cache()
    add_libraries(cache, ['libcat.so', 'libdog.so', 'libbird.so', 'libsquirrel.so'])
    cache.add_dependency('libdog.so', 'libcat.so')
    cache.add_dependency('libdog.so', 'libbird.so')
    cache.add_dependency('libdog.so', 'libsquirrel.so')
    cache.add_dependency('libcat.so', 'libbird.so')

    res = ut.minimize_dependencies_list(cache, ['libdog.so', 'libcat.so', 'libbird.so'])
    assert res == ['libdog.so']

    res = ut.minimize_dependencies_list(cache, ['libcat.so', 'libdog.so'])
    assert res == ['libdog.so']

    res = ut.minimize_dependencies_list(cache, ['libcat.so', 'libbird.so'])
    assert res == ['libcat.so']

    # check all dependencies are removed
    res = ut.minimize_dependencies_list(cache, ['libdog.so', 'libcat.so', 'libsquirrel.so'])
    assert res == ['libdog.so']

    # even if intermediate dep is not in list, prune the leaves
    res = ut.minimize_dependencies_list(cache, ['libdog.so', 'libbird.so'])
    assert res == ['libdog.so']

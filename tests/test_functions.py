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
    """
    graph {
        lib1.so -> lib2.so -> lib5.so;
        lib1.so -> lib3.so -> lib4.so;
        lib2.so -> lib4.so;
    }
    """
    cache = Cache()
    add_libraries(cache, ['lib1.so', 'lib2.so', 'lib3.so', 'lib4.so', 'lib5.so'])
    cache.add_dependency('lib1.so', 'lib2.so')
    cache.add_dependency('lib1.so', 'lib3.so')
    cache.add_dependency('lib2.so', 'lib4.so')
    cache.add_dependency('lib3.so', 'lib4.so')
    cache.add_dependency('lib2.so', 'lib5.so')

    # single leaf
    graph = ut.create_libs_graph(cache, ['lib5.so'])
    assert graph.keys == {'lib5.so'}

    # one arg with two children
    graph = ut.create_libs_graph(cache, ['lib2.so'])
    assert graph.keys == {'lib2.so', 'lib4.so', 'lib5.so'}

    # two children, one in arguments
    graph = ut.create_libs_graph(cache, ['lib5.so', 'lib2.so'])
    assert graph.keys == {'lib2.so', 'lib4.so', 'lib5.so'}

    # one child
    graph = ut.create_libs_graph(cache, ['lib3.so'])
    assert graph.keys == {'lib3.so', 'lib4.so'}

    # the root
    graph = ut.create_libs_graph(cache, ['lib1.so'])
    assert graph.keys == {'lib1.so', 'lib2.so', 'lib3.so', 'lib4.so', 'lib5.so'}

    # the root and some other node in arguments
    graph = ut.create_libs_graph(cache, ['lib5.so', 'lib3.so', 'lib1.so'])
    assert graph.keys == {'lib1.so', 'lib2.so', 'lib3.so', 'lib4.so', 'lib5.so'}


def test_create_graph_with_non_libraries():
    cache = Cache()
    add_libraries(cache, ['lib1.so', 'lib2.so', 'lib3.so', 'lib4.so'])
    cache.add_dependency('lib1.so', 'lib2.so')
    cache.add_dependency('lib1.so', 'lib3.so')
    cache.add_dependency('lib2.so', 'lib4.so')
    cache.set_component_libraries('comp', ['lib3.so', 'lib4.so'])

    with pytest.raises(Exception):
        ut.create_libs_graph(cache, ['lib1.so', 'comp'])


def node_children(graph: DepGraph, id: str):
    return {n.name for n in graph.get_node(id).out_refs}


def test_create_graph_with_components():
    """
    graph {
        lib1.so -> lib2.so;
        lib1.so -> lib3.so (comp) -> lib5.so;
        lib1.so -> lib4.so (comp) -> lib6.so;
    }
    """
    cache = Cache()
    add_libraries(cache, [f'lib{i}.so' for i in range(1, 7)])
    cache.add_dependency('lib1.so', 'lib2.so')
    cache.add_dependency('lib1.so', 'lib3.so')
    cache.add_dependency('lib1.so', 'lib4.so')
    cache.add_dependency('lib3.so', 'lib5.so')
    cache.add_dependency('lib4.so', 'lib6.so')
    cache.set_component_libraries('comp', ['lib3.so', 'lib4.so'])

    graph = ut.create_libs_graph(cache, ['lib1.so'])
    ut.replace_libs_with_components(cache, graph)
    print(graph.to_dot())

    assert set(graph.keys) == {'comp', 'lib1.so', 'lib2.so', 'lib5.so', 'lib6.so'}

    assert node_children(graph, 'comp') == {'lib5.so', 'lib6.so'}
    assert node_children(graph, 'lib1.so') == {'lib2.so', 'comp'}
    assert node_children(graph, 'lib2.so') == set()


def test_create_graph_with_more_components():
    """
    graph {
        lib1.so -> lib2.so;
        lib1.so -> lib3.so -> lib5.so -> lib8.so;
                   lib3.so -> lib6.so;
        lib1.so -> lib4.so -> lib6.so;
                   lib4.so -> lib7.so;
    }
    """
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

    graph = ut.create_libs_graph(cache, ['lib1.so'])
    ut.replace_libs_with_components(cache, graph)
    print(graph.to_dot())

    assert set(graph.keys) == {'comp34', 'comp56', 'comp7', 'lib1.so', 'lib2.so', 'lib8.so'}

    assert node_children(graph, 'lib1.so') == {'lib2.so', 'comp34'}
    assert node_children(graph, 'comp34') == {'comp56', 'comp7'}
    assert node_children(graph, 'comp56') == {'lib8.so'}
    assert node_children(graph, 'lib2.so') == set()
    assert node_children(graph, 'lib8.so') == set()
    assert node_children(graph, 'comp7') == set()


@pytest.mark.timeout(5)
def test_create_graph_with_components_with_internal_dependencies():
    """
    graph {
        lib1.so -> lib2.so (x) -> lib5.so (x) -> lib6.so;
        lib1.so -> lib3.so (x);
        lib1.so -> lib4.so -> lib5.so (x);
    }
    """
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
    ut.replace_libs_with_components(cache, graph)
    print(graph.to_dot())

    assert set(graph.keys) == {'compx', 'lib1.so', 'lib4.so', 'lib6.so'}
    assert node_children(graph, 'lib1.so') == {'compx', 'lib4.so'}
    assert node_children(graph, 'lib4.so') == {'compx'}
    assert node_children(graph, 'compx') == {'lib6.so'}
    assert node_children(graph, 'lib6.so') == set()


def test_sort_libraries():
    cache = Cache()
    add_libraries(cache, ['libcat.so', 'libdog.a', 'libbird.so'])
    cache.add_dependency('dog', 'cat')
    cache.add_dependency('cat', 'bird')

    res = ut.sort_by_dependency(cache, ['bird', 'cat', 'dog'])
    assert res == ['dog', 'cat', 'bird']

    assert ut.sort_by_dependency(cache, ['bird', 'dog'], add_dependencies=True) == ['dog', 'cat', 'bird']

    assert ut.sort_by_dependency(cache, ['bird', 'cat'], add_dependencies=True) == ['cat', 'bird']


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

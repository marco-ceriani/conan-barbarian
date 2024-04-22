from conan_barbarian.data import Cache
from conan_barbarian.graphs import DepGraph
from conan_barbarian.libshelper import sort_by_dependency, sort_graph

# Graph sorting

def test_graph_sort_1():
    graph = DepGraph()
    graph.add_dependency('A', 'B')
    graph.add_dependency('A', 'C')
    graph.add_dependency('B', 'D')

    a_deps = sort_graph(graph)
    assert a_deps == ['A', 'B', 'C', 'D']

def test_graph_sort_case_2():
    graph = DepGraph()
    graph.add_dependency('R', 'E')
    graph.add_dependency('A', 'M')
    graph.add_dependency('D', 'R')
    graph.add_dependency('E', 'A')

    sorted_libs = sort_graph(graph)
    assert sorted_libs == ['D', 'R', 'E', 'A', 'M']

def test_graph_sort_case_3():
    graph = DepGraph()
    graph.add_dependency('M', 'N')
    graph.add_dependency('N', 'O')
    graph.add_dependency('A', 'B')
    graph.add_dependency('B', 'C')

    sorted_libs = sort_graph(graph)
    assert sorted_libs == ['A', 'M', 'B', 'N', 'C', 'O']

# Up one logic level: sort libraries from cache

def define_libs(cache: Cache, libs):
    for lib in libs:
        cache.add_library(lib)

def test_libs_sort_case_2():
    cache = Cache()
    define_libs(cache, ['D', 'R', 'E', 'A', 'M'])
    cache.add_dependency('D', 'R')
    cache.add_dependency('R', 'E')
    cache.add_dependency('E', 'A')
    cache.add_dependency('A', 'M')

    sorted_libs = sort_by_dependency(cache, ['A', 'D', 'E', 'M', 'R'])
    assert sorted_libs == ['D', 'R', 'E', 'A', 'M']

def test_libs_sort_case_3():
    cache = Cache()
    define_libs(cache, ['A', 'B', 'C', 'M', 'N', 'O'])
    cache.add_dependency('A', 'B')
    cache.add_dependency('B', 'C')
    cache.add_dependency('M', 'N')
    cache.add_dependency('N', 'O')

    sorted_libs = sort_by_dependency(cache, ['A', 'B', 'C', 'M', 'N', 'O'])
    assert sorted_libs == ['A', 'M', 'B', 'N', 'C', 'O']

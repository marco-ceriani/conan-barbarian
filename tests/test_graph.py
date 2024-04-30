from conan_barbarian.data import Cache
from conan_barbarian.graphs import DepGraph, prune_arcs, sort_graph
from conan_barbarian.libshelper import sort_by_dependency


def test_graph_manipulation():
    graph = DepGraph()
    graph.add_dependency('A', 'B')
    assert graph.get_node('A').out_ids == ['B']

    a = graph.get_node('A')
    graph.get_node('B').remove_in_ref(a)
    assert graph.get_node('A').out_refs == set()
    assert graph.get_node('B').in_refs == set()


def test_graph_visit():
    graph = DepGraph()
    graph.add_dependency('A', 'B')
    graph.add_dependency('A', 'C')
    graph.add_dependency('B', 'D')

    visited = []
    arcs = set()
    graph.traverse(lambda n: visited.append(n.name),
                   lambda src, tgt : arcs.add(f'{src.name}-{tgt.name}'))
    assert visited == ['A', 'B', 'C', 'D']
    assert arcs == {'A-B', 'A-C', 'B-D'}


# Graph sorting

def test_graph_sort_1():
    """
    graph {
        A->B->D;
        A->C;
    }
    """
    graph = DepGraph()
    graph.add_dependency('A', 'B')
    graph.add_dependency('A', 'C')
    graph.add_dependency('B', 'D')

    a_deps = sort_graph(graph)
    assert a_deps == ['A', 'B', 'C', 'D']

    for node in graph.nodes:
        assert len(node.data) == 0


def test_graph_sort_case_2():
    """
    graph {
        D->R->E->A->M;
    }
    with dependencies added in a different order
    """
    graph = DepGraph()
    graph.add_dependency('R', 'E')
    graph.add_dependency('A', 'M')
    graph.add_dependency('D', 'R')
    graph.add_dependency('E', 'A')

    sorted_libs = sort_graph(graph)
    assert sorted_libs == ['D', 'R', 'E', 'A', 'M']


def test_graph_sort_case_3():
    """
    two distinct graphs
    graph {
        M->N->O;
        A->B->C;
    }
    """
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
    """
    Special graph: all linearly sorted D->R->E->A->M
    """
    cache = Cache()
    define_libs(cache, ['D', 'R', 'E', 'A', 'M'])
    cache.add_dependency('D', 'R')
    cache.add_dependency('R', 'E')
    cache.add_dependency('E', 'A')
    cache.add_dependency('A', 'M')

    sorted_libs = sort_by_dependency(cache, ['A', 'D', 'E', 'M', 'R'])
    assert sorted_libs == ['D', 'R', 'E', 'A', 'M']


def test_libs_sort_case_3():
    """
    Two separate graphs A->B->C / M->N->O
    """
    cache = Cache()
    define_libs(cache, ['A', 'B', 'C', 'M', 'N', 'O'])
    cache.add_dependency('A', 'B')
    cache.add_dependency('B', 'C')
    cache.add_dependency('M', 'N')
    cache.add_dependency('N', 'O')

    sorted_libs = sort_by_dependency(cache, ['A', 'B', 'C', 'M', 'N', 'O'])
    assert sorted_libs == ['A', 'M', 'B', 'N', 'C', 'O']


# Prune arcs


def test_graph_pruning_tree():
    """
    graph {
        A -> B -> E;
             B -> F;
        A -> C -> G
        A -> D;
    }
    """
    graph = DepGraph()
    graph.add_dependency('A', 'B')
    graph.add_dependency('A', 'C')
    graph.add_dependency('A', 'D')
    graph.add_dependency('B', 'E')
    graph.add_dependency('B', 'F')
    graph.add_dependency('C', 'G')


    pruned = prune_arcs(graph)
    print(pruned.to_dot())

    assert pruned.keys == frozenset({'A', 'B', 'C', 'D', 'E', 'F', 'G'})
    assert set(pruned.get_node('A').out_ids) == {'B', 'C', 'D'}
    assert set(pruned.get_node('B').out_ids) == {'E', 'F'}
    assert set(pruned.get_node('C').out_ids) == {'G'}
    assert set(pruned.get_node('D').out_ids) == set()


def test_graph_pruning_simple_case():
    """
    graph {
        A -> B -> C;
        A -> C;
    }
    """
    graph = DepGraph()
    graph.add_dependency('A', 'B')
    graph.add_dependency('A', 'C')
    graph.add_dependency('B', 'C')

    #import pdb
    #pdb.set_trace()
    pruned = prune_arcs(graph)
    print(pruned.to_dot())

    assert pruned.keys == frozenset({'A', 'B', 'C'})
    assert set(pruned.get_node('A').out_ids) == {'B'}
    assert set(pruned.get_node('B').out_ids) == {'C'}
    assert set(pruned.get_node('C').out_ids) == set()


def test_graph_pruning_all_way_down():
    graph = DepGraph()
    graph.add_dependency('A', 'B')
    graph.add_dependency('A', 'C')
    graph.add_dependency('A', 'D')
    graph.add_dependency('A', 'E')
    graph.add_dependency('B', 'C')
    graph.add_dependency('B', 'D')
    graph.add_dependency('B', 'E')
    graph.add_dependency('C', 'D')
    graph.add_dependency('C', 'E')
    graph.add_dependency('D', 'E')

    pruned = prune_arcs(graph)
    print(pruned.to_dot())

    assert pruned.keys == frozenset({'A', 'B', 'C', 'D', 'E'})
    assert set(pruned.get_node('A').out_ids) == {'B'}
    assert set(pruned.get_node('B').out_ids) == {'C'}
    assert set(pruned.get_node('C').out_ids) == {'D'}
    assert set(pruned.get_node('D').out_ids) == {'E'}
    


import pytest
from libshelper import Cache, sort_by_dependency
from pathlib import Path


def test_graph_sort_1(tmp_path):
    cache = Cache(Path(tmp_path, 'cache'))
    cache.add_dependency('A', 'B')
    cache.add_dependency('A', 'C')
    cache.add_dependency('B', 'D')

    a_deps = sort_by_dependency(cache, ['A', 'B', 'C', 'D'])
    assert a_deps == ['A', 'B', 'C', 'D']

def test_graph_sort_case_2(tmp_path):
    cache = Cache(Path(tmp_path, 'cache'))
    cache.add_dependency('D', 'R')
    cache.add_dependency('R', 'E')
    cache.add_dependency('E', 'A')
    cache.add_dependency('A', 'M')

    sorted_libs = sort_by_dependency(cache, ['A', 'D', 'E', 'M', 'R'])
    assert sorted_libs == ['D', 'R', 'E', 'A', 'M']

def test_graph_sort_case_3(tmp_path):
    cache = Cache(Path(tmp_path, 'cache'))
    cache.add_dependency('A', 'B')
    cache.add_dependency('B', 'C')
    cache.add_dependency('M', 'N')
    cache.add_dependency('N', 'O')

    sorted_libs = sort_by_dependency(cache, ['A', 'B', 'C', 'M', 'N', 'O'])
    assert sorted_libs == ['A', 'M', 'B', 'N', 'C', 'O']

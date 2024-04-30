from conan_barbarian.data import Library, Cache
import pytest
from pathlib import Path


def all_lib_names(cache: Cache):
    return [lib.name for lib in cache.list_libraries()]


def test_adding_libraries():
    cache = Cache()
    cache.add_library('foo')
    cache.add_library('libbar.so')

    assert cache.is_library('foo')
    assert cache.is_library('bar')
    assert not cache.is_library('qux')

    lib_names = all_lib_names(cache)
    assert 'foo' in lib_names
    assert 'bar' in lib_names
    assert 'libbar.so' in cache.all_library_files()
    assert not 'qux' in lib_names


def test_adding_system_libraries():
    cache = Cache()
    cache.add_library('libssl.so', system=True)
    cache.add_library('libboost_regex.so')

    assert cache.is_library('ssl')
    lib_names = all_lib_names(cache)
    assert 'ssl' in lib_names
    assert 'boost_regex' in lib_names
    assert 'libssl.so' in cache.all_library_files()

    ssl_lib = cache.get_library('ssl')
    assert ssl_lib
    assert ssl_lib.system
    assert not cache.get_library('boost_regex').system


def test_find_library():
    cache = Cache()
    cache.add_library('libssl.so')
    cache.add_library('libmath.a')

    assert cache.find_library('ssl') == 'libssl.so'
    assert cache.find_library('libssl.so') == 'libssl.so'
    assert cache.find_library('libssl.a') is None

    assert cache.find_library('math') == 'libmath.a'
    assert cache.find_library('libmath.so') is None
    assert cache.find_library('libmath.a') == 'libmath.a'

    assert cache.find_library('icecream') is None


def test_get_library():
    cache = Cache()
    cache.add_library('libssl.so')
    cache.add_library('libmath.a')

    dynlib = Library('libssl.so')
    assert cache.get_library('ssl') == dynlib
    assert cache.get_library('libssl.so') == dynlib
    assert cache.get_library('libssl.a') is None

    staticlib = Library('libmath.a')
    assert cache.get_library('math') == staticlib
    assert cache.get_library('libmath.so') is None
    assert cache.get_library('libmath.a') == staticlib

    assert cache.get_library('potato') is None


def test_add_dependencies():
    cache = Cache()
    cache.add_library('libfoo.so')
    cache.add_library('libbar.a')
    cache.add_dependency('foo', 'libbar.a')

    deps = cache.get_dependencies('foo')
    assert deps == {'libbar.a'}


def test_add_dependencies_with_filename():
    cache = Cache()
    cache.add_library('libfoo.so')
    cache.add_library('libbar.a')
    cache.add_library('libquz.so')
    cache.add_dependency('libfoo.so', 'libbar.a')
    cache.add_dependency('libfoo.so', 'libquz.so')

    deps = cache.get_dependencies('foo')
    assert len(deps) == 2
    assert deps == {'libbar.a', 'libquz.so'}


def test_transitive_dependencies():
    cache = Cache()
    cache.add_library('libfoo.so')
    cache.add_library('libbar.a')
    cache.add_dependency('libfoo.so', 'libbar.a')
    cache.add_library('libquz.so')
    cache.add_dependency('libbar.a', 'libquz.so')

    deps = cache.get_dependencies('foo')
    assert deps == {'libbar.a'}
    deps = cache.get_dependencies('foo', transitive=True)
    assert deps == {'libbar.a', 'libquz.so'}

    # assert that original dependencies are not modified
    assert cache.get_library('foo').dependencies == {'libbar.a'}
    assert cache.get_library('bar').dependencies == {'libquz.so'}


def test_dependencies_of_invalid_name_throws():
    cache = Cache()
    cache.add_library('libfoo.a')
    with pytest.raises(Exception):
        cache.get_dependencies('libfoobar.so')


def test_cache_io(tmp_path):
    data_path = Path(tmp_path, 'cache.data')

    cache = Cache(data_path)
    cache.add_library('libcoffee.so')
    cache.add_library('libparty.a', system=True)
    cache.add_dependency('party', 'libboost_coffee.so')
    cache.save()

    with open(data_path) as f:
        print(f.read())

    cache2 = Cache(data_path)
    cache2.load()
    assert len(cache2.list_libraries()) == 2

    lib1 = cache2.get_library('coffee')
    assert lib1 is not None
    assert isinstance(lib1, Library)
    assert lib1.name == 'coffee'
    assert lib1.filename == 'libcoffee.so'
    assert lib1.system == False

    lib2 = cache2.get_library('party')
    assert lib2 is not None
    assert isinstance(lib2, Library)
    assert lib2.name == 'party'
    assert lib2.filename == 'libparty.a'
    assert lib2.system == True


### Symbols Management


def test_components():
    cache = Cache()
    for lib in ['librabbit.so', 'libbird.so', 'libwolf.so']:
        cache.add_library(lib)
    cache.set_component_libraries('c1', ['libbird.so', 'libwolf.so'])

    assert set(cache.get_component_libraries('c1')) == {'libbird.so', 'libwolf.so'}
    assert cache.get_library_component('libbird.so') == 'c1'
    assert cache.get_library_component('libwolf.so') == 'c1'
    assert cache.get_library_component('librabbit.so') is None


### Symbols Management


def test_symbols_definition():
    cache = Cache()
    cache.add_library('libdream.so')
    cache.define_symbol('dream::catchIt()', 'libdream.so')

    assert cache.get_library_defining_symbol('dream::catchIt()') == 'libdream.so'
    assert cache.get_library_defining_symbol('printf') is None


def test_symbols_definition_with_depending_libs():
    cache = Cache()
    cache.add_library('libchase.a')
    cache.add_undefined_symbol_dependency('dream::catchIt()', 'libchase.a')
    cache.add_library('libdream.so')
    depending_libs = cache.define_symbol('dream::catchIt()', 'libdream.so')

    assert cache.get_library_defining_symbol('dream::catchIt()') == 'libdream.so'
    assert depending_libs == {'libchase.a'}


def test_find_undefined_symbo():
    cache = Cache()
    cache.add_undefined_symbol_dependency('dance::foo_bar()', 'libdance.a')
    cache.add_library('libsing.so')
    depending = cache.define_symbol('dance::foo_bar()', 'libsing.so')

    assert depending == {'libdance.a'}


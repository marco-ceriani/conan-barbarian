from conan_barbarian.data import Cache
from conan_barbarian.scraping import _parse_nm_output, _update_cache


def test_parse_nm():
    b1 = "namespace::clazz::_default_instance_"
    s1 = "namespace::clazz::method(int, int)"
    s2 = "namespace::clazz::another_method(unsigned int)"
    dump = f"""
0000000000000090 B {b1}
0000000000001090 T {s1}
0000000000001140 T {s2}
                 U memset
                 U strlen
"""
    defined, undefined = _parse_nm_output(dump)
    assert set(defined) == {s1, s2, b1}
    assert set(undefined) == {'memset', 'strlen'}


def test_parse_nm_strange_case_ut():
    dump = """
000000000000e620 T ns1::ns2::ClaZz::a_magic_methodr() const
                 U ns1::ns2::ClaZz::a_magic_methodr() const
"""
    defined, undefined = _parse_nm_output(dump)
    assert defined == ['ns1::ns2::ClaZz::a_magic_methodr() const']
    assert undefined == []


def test_update_cache_first_lib():
    s1 = "func1(int, int)"
    s2 = "func2(unsigned int)"
    u1 = 'my_func()'

    cache = Cache()
    _update_cache(cache, 'libfoo.so', [s1, s2], [u1])

    assert cache.all_library_files() == ['libfoo.so']
    assert cache.defined_symbols.keys() == {s1, s2}
    assert cache.undefined_symbols.keys() == {u1}
    assert cache.defined_symbols[s1] == 'libfoo.so'
    assert cache.defined_symbols[s2] == 'libfoo.so'
    assert cache.undefined_symbols[u1] == {'libfoo.so'}


def test_update_cache_find_deps():
    s1 = "func1(int, int)"
    s2 = "func2(unsigned int)"
    s3 = 'my_func()'

    cache = Cache()
    _update_cache(cache, 'librabbit.so', [s1], [s3])
    _update_cache(cache, 'libtortoise.so', [s2, s3], [])

    assert set(cache.all_library_files()) == {'librabbit.so', 'libtortoise.so'}
    assert cache.defined_symbols.keys() == {s1, s2, s3}
    assert cache.undefined_symbols.keys() == set()
    assert cache.defined_symbols[s1] == 'librabbit.so'
    assert cache.defined_symbols[s2] == 'libtortoise.so'
    assert cache.defined_symbols[s3] == 'libtortoise.so'
    assert cache.get_library('librabbit.so').dependencies == {'libtortoise.so'}


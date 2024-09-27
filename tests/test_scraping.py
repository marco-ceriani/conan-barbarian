from conan_barbarian.data import Cache
from conan_barbarian.scraping import _parse_nm_output, _parse_link_script, _update_cache
from pathlib import Path


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


def test_parse_ld_script(tmpdir):
    script = """
/* GNU ld script
comment here GROUP ( /lib64/libsurprise.so )
comment end */
OUTPUT_FORMAT(elf64-x86-64)
INPUT ( /lib64/libpthread.so )
GROUP ( /lib64/libm.so.6  AS_NEEDED ( /lib64/libmvec.so.1 ) )
"""
    script_path = Path(tmpdir, 'script.so')
    with script_path.open('w') as f:
        f.write(script)

    libs = _parse_link_script(script_path)
    assert set(libs) == {'/lib64/libm.so.6', '/lib64/libpthread.so'}


def test_update_cache_first_lib():
    s1 = "func1(int, int)"
    s2 = "func2(unsigned int)"
    u1 = 'my_func()'

    cache = Cache()
    _update_cache(cache, 'libfoo.so', [s1, s2], [u1])

    assert cache.all_library_files() == ['libfoo.so']
    assert cache.defined_symbols == {s1, s2}
    assert cache.undefined_symbols == {u1}
    assert cache.get_library_defining_symbol(s1) == 'libfoo.so'
    assert cache.get_library_defining_symbol(s2) == 'libfoo.so'
    assert cache.libraries_needing_undefined_symbol(u1) == {'libfoo.so'}


def test_update_cache_libs_in_order():
    s1 = "func1(int, int)"
    s2 = "func2(unsigned int)"
    s3 = 'my_func()'

    cache = Cache()
    _update_cache(cache, 'librabbit.so', [s1], [])
    _update_cache(cache, 'libbird.so', [s2], [s1])
    _update_cache(cache, 'libwolf.so', [s3], [s2])

    assert cache.all_library_files() == ['librabbit.so', 'libbird.so', 'libwolf.so']
    assert cache.defined_symbols == {s1, s2, s3}
    assert cache.undefined_symbols == set()
    assert cache.get_library_defining_symbol(s1) == 'librabbit.so'
    assert cache.get_library_defining_symbol(s2) == 'libbird.so'
    assert cache.get_library_defining_symbol(s3) == 'libwolf.so'
    assert set(cache.get_library('bird').dependencies) == { 'librabbit.so' }
    assert set(cache.get_library('wolf').dependencies) == { 'libbird.so' }


def test_update_cache_find_deps():
    s1 = "func1(int, int)"
    s2 = "func2(unsigned int)"
    s3 = 'my_func()'

    cache = Cache()
    _update_cache(cache, 'librabbit.so', [s1], [s3])
    _update_cache(cache, 'libtortoise.so', [s2, s3], [])

    assert set(cache.all_library_files()) == {'librabbit.so', 'libtortoise.so'}
    assert cache.defined_symbols == {s1, s2, s3}
    assert cache.undefined_symbols == set()
    assert cache.get_library_defining_symbol(s1) == 'librabbit.so'
    assert cache.get_library_defining_symbol(s2) == 'libtortoise.so'
    assert cache.get_library_defining_symbol(s3) == 'libtortoise.so'
    assert cache.get_library('librabbit.so').dependencies == {'libtortoise.so'}


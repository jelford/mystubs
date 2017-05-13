"""
update.py

Usage:
    update.py [--clean]

Options:
    --clean     Remove all previous output
"""
from typing import Iterator, Dict, Any, Callable, List

import os
from os import path

import pkgutil
import subprocess
import shutil
from importlib.util import find_spec
import hashlib
import re
import functools
import sys
import itertools
import tempfile

import toml
import appdirs
from docopt import docopt

config: Dict[str, Any] = {
    'local_stubs_directory': '.mystubs',
    'discover_modules': False,
    'modules': dict()
}

_appdirs = appdirs.AppDirs(appname='mystubs')

_REQUIREMENT_SPEC = re.compile('(?P<name>[_a-zA-Z0-9]+)[=><~]+(?P<version>.+)')


@functools.lru_cache()
def mypy_version():
    from mypy.version import __version__ as mypy_version
    return mypy_version


@functools.lru_cache()
def auto_versions():
    requirements_files = config.get('requirements_paths', ['requirements.txt'])
    packages: Dict[str, str] = dict()
    for r_path in requirements_files:
        with open(r_path, 'r', encoding='utf-8') as f:
            for line in f:
                spec = _REQUIREMENT_SPEC.match(line)
                if spec is None:
                    continue

                packages[spec.group(1)] = spec.group(2)
    return packages


@functools.lru_cache()
def auto_version(package_name):
    return auto_versions().get(package_name)


class Mod():
    def __init__(self, name: str, config: Dict[str, str], stub_root_dir: str) -> None:
        self.config = config
        self.name = name
        self.stub_root_dir = stub_root_dir

    @property
    def package_name(self) -> str:
        return self.config.get('package_name', self.name)

    @property
    def target_version(self) -> str:
        version = self.config.get('version', 'auto')
        if version == 'auto':
            return auto_version(self.name)
        return version

    @property
    def prev_build_record_path(self) -> str:
        return path.join(config['local_stubs_directory'], '.state', self.name, 'build.version')

    @property
    def project_local_stubs_overrides(self) -> str:
        return path.join(config['local_stubs_directory'], '.local', self.name)

    @property
    def user_local_stubs_override_dirs(self) -> List[str]:
        py_maj, py_min, *_ = sys.version_info
        return [
            path.join(_appdirs.user_config_dir, 'local', str(py_maj), self.name),
            path.join(_appdirs.user_config_dir, 'local', f'{py_maj}.{py_min}', self.name)
        ]

    def hash_current_state(self, hasher: Callable[[bytes], None]) -> None:
        hasher(mypy_version().encode('utf-8'))
        hasher(self.target_version.encode('utf-8'))
        hash_dir(hasher, self.project_local_stubs_overrides)
        for artifact in [f'{self.package_name}.pyi', self.package_name]:
            art_target = path.join(config['local_stubs_directory'], artifact)
            if path.isdir(art_target):
                hash_dir(hasher, art_target)
            elif path.isfile(art_target):
                hash_file(hasher, art_target)


def gather_submodules(mod_paths, prefix):
    for _, name, ispkg in pkgutil.walk_packages(mod_paths, f'{prefix}.'):
        if '._' not in name:
            yield name


def gather_stubgen_jobs(module_name):
    module_spec = find_spec(module_name)

    if module_spec is None:
        print(f"Couldn't find anything to build for {module_name}")
        return

    yield module_spec.name
    if module_spec.submodule_search_locations is None:
        return

    yield from gather_submodules(module_spec.submodule_search_locations, module_name)


def gather_modules_to_build() -> Iterator[Mod]:
    local_dir = path.join(config['local_stubs_directory'], '.local')
    configured_modules = set()

    for mod, details in config['modules'].items():
        configured_modules.add(mod)

        try:
            skip = details.get('skip', False)
        except AttributeError:
            skip = False
            details = {'version': details}

        if not skip:
            yield(Mod(mod, details, path.join(local_dir, mod)))

    if config['discover_modules']:
        for mod, version in auto_versions().items():
            if mod in configured_modules:
                continue
            yield Mod(mod, {'version': version}, path.join(local_dir, mod))


def kill(kill_path):
    if not path.exists(kill_path):
        return
    if path.islink(kill_path):
        os.remove(kill_path)
    if path.isfile(kill_path):
        os.remove(kill_path)
    if path.isdir(kill_path):
        shutil.rmtree(kill_path)


def ensure_dir(dir_path: str) -> None:
    try:
        os.makedirs(dir_path)
    except FileExistsError:
        pass


def generate_stubs(mod, target_dir) -> None:
    print(f'Building stubs for {mod.name}')

    with tempfile.TemporaryDirectory() as d:
        ensure_dir(path.join(d, 'out'))
        for p in gather_stubgen_jobs(mod.package_name):
            subprocess.check_call(['stubgen', p], stdout=subprocess.DEVNULL, stderr=None, cwd=d)
        copy_stubs_into_place(path.join(d, 'out'))


_allowed_hashes = {
    'blake2b': hashlib.blake2b
}


def hash_file(hasher, file_to_hash):
    with open(file_to_hash, 'rb') as f:
        hasher(file_to_hash.encode('utf-8'))
        hasher(f.read())


def hash_dir(hasher: Callable, dir: str) -> None:
    item_count = 0
    hasher(bytes([1 if dir is not None and path.exists(dir) else 0]))
    if dir is None:
        return

    for root, dirs, files in os.walk(dir):
        hasher(root.encode('utf-8'))
        item_count += 1

        dirs[:] = sorted(dirs)
        files = sorted(files)
        for f_tohash in files:
            item_count += 1
            hash_file(hasher, path.join(root, f_tohash))

    hasher(bytes([item_count]))


def is_built_version(mod: Mod, target: str) -> bool:
    if target is None:
        return False

    try:
        build_record = toml.load(mod.prev_build_record_path)
    except FileNotFoundError:
        return False

    built_version = build_record['version']
    if built_version != target:
        return False

    alleged_built_hash = build_record['hash']
    hash_algo = build_record['hash_algo']

    try:
        hasher = _allowed_hashes[hash_algo]()
    except KeyError:
        return False

    mod.hash_current_state(hasher.update)
    actual_built_hash = hasher.hexdigest()

    return alleged_built_hash == actual_built_hash


def record_build_state(mod: Mod) -> None:
    hasher = hashlib.blake2b()
    mod.hash_current_state(hasher.update)
    build_record = {
        'version': mod.target_version,
        'hash': hasher.hexdigest(),
        'hash_algo': 'blake2b',
    }

    ensure_dir(path.dirname(mod.prev_build_record_path))
    with open(mod.prev_build_record_path, 'w') as record:
        mod.config.update(build_record)
        toml.dump(mod.config, record)


def copy_stubs_into_place(from_dir: str) -> None:
    if from_dir is None or not path.exists(from_dir):
        return

    target = config['local_stubs_directory']
    for root, _, fnames in os.walk(from_dir):
        root = path.relpath(root, start=from_dir)
        out_folder = path.abspath(path.join(target, root))

        for f in fnames:
            ensure_dir(out_folder)
            out_file = path.abspath(path.join(out_folder, f))
            in_file = path.abspath(path.join(from_dir, root, f))
            shutil.copy2(in_file, out_file)


def update_if_required(mod: Mod) -> None:

    if is_built_version(mod, mod.target_version):
        print(f'{mod.name} is up to date')
        return

    generate_stubs(mod, config['local_stubs_directory'])

    for p in itertools.chain(mod.user_local_stubs_override_dirs,
                             [mod.project_local_stubs_overrides]):

        copy_stubs_into_place(p)

    record_build_state(mod)


def run() -> None:
    global config
    config.update(toml.load('.mystubs.toml'))

    args = docopt(__doc__)
    if args['--clean']:
        clean()
        return

    for mod in gather_modules_to_build():
        update_if_required(mod)


def clean():
    local_stubs_dir = config['local_stubs_directory']
    for output in os.listdir(local_stubs_dir):
        if output == '.local':
            continue
        kill(path.join(local_stubs_dir, output))


if __name__ == '__main__':
    run()

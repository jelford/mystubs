
from typing import Iterator, Dict, Any

import os
from os import path

import toml
import pygit2 as git
import tempfile
import venv
import pkgutil
import subprocess
import shutil
from importlib.util import find_spec
import hashlib
import re
import functools

config: Dict[str, Any] = dict()

_REQUIREMENT_SPEC = re.compile('(?P<name>[_a-zA-Z]+)[=><~]+(?P<version>.+)')


def stubs_link(mod_name):
    return path.join('.mystubs', mod_name)


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
    def stub_out_dir(self) -> str:
        return path.join(self.stub_root_dir, 'out', self.name)

    @property
    def target_version(self) -> str:
        version = self.config.get('version', 'auto')
        if version == 'auto':
            return auto_version(self.name)
        return version

    @property
    def prev_build_record_path(self) -> str:
        return path.join(self.stub_root_dir, 'build.version')


def gather_submodules(mod_paths, prefix):
    for _, name, ispkg in pkgutil.walk_packages(mod_paths, f'{prefix}.'):
        if '._' not in name:
            yield name


def gather_stubgen_jobs(module_name):
    module_spec = find_spec(module_name)

    if module_spec is None:
        return

    yield module_spec.name
    if module_spec.submodule_search_locations is None:
        return

    yield from gather_submodules(module_spec.submodule_search_locations, module_name)


def gather_modules_to_build() -> Iterator[Mod]:
    for mod, details in config.items():
        try:
            skip = details.get('skip', False)
        except AttributeError:
            skip = False
            details = {'version': details}

        if not skip:
            yield(Mod(mod, details, path.join('.mystubs', '.work', mod)))


def kill(kill_path):
    if not path.exists(kill_path):
        return
    if path.islink(kill_path):
        os.remove(kill_path)
    if path.isfile(kill_path):
        os.remove(kill_path)
    if path.isdir(kill_path):
        shutil.rmtree(kill_path)


def clear_previous_output(mod):
    kill(stubs_link(mod.name))
    kill(mod.stub_out_dir)
    kill(mod.prev_build_record_path)
    os.makedirs(mod.stub_out_dir)


def do_update(mod) -> None:
    clear_previous_output(mod)
    print(f'Building stubs for {mod.name}')

    for p in gather_stubgen_jobs(mod.name):
        subprocess.check_call(['stubgen', p], stdout=None, stderr=None, cwd=mod.stub_root_dir)

    link_location = stubs_link(mod.name)
    os.symlink(path.relpath(mod.stub_out_dir, start=path.dirname(link_location)), link_location)


_allowed_hashes = {
    'blake2b': hashlib.blake2b
}


def hash_dir(hash_algo, dir):
    hasher = _allowed_hashes[hash_algo]()
    for root, dirs, files in os.walk(dir):
        dirs[:] = sorted(dirs)
        files = sorted(files)
        for f_tohash in files:
            with open(path.join(root, f_tohash), 'r') as f:
                hasher.update(f)
    return hasher.hexdigest()


def is_built_version(mod, target):
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
    if hash_algo not in _allowed_hashes:
        return False

    actual_built_hash = hash_dir(hash_algo, mod.stub_out_dir)

    return alleged_built_hash == actual_built_hash


def update_if_required(mod) -> None:
    if is_built_version(mod, mod.target_version):
        print(f'{mod.name} is up to date')
        return
    do_update(mod)
    build_record = {
        'version': mod.target_version,
        'hash': hash_dir('blake2b', mod.stub_out_dir),
        'hash_algo': 'blake2b',
    }
    with open(mod.prev_build_record_path, 'w') as record:
        toml.dump(build_record, record)


def run() -> None:
    global config
    config = toml.load('.mystubs.toml')
    for mod in gather_modules_to_build():
        update_if_required(mod)


if __name__ == '__main__':
    run()
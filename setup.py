from setuptools import setup, find_packages
import json


def load_requirements():
    with open('Pipfile.lock', 'rb') as lockfile:
        lock_data = json.load(lockfile)
    return [
        f'{rname}{rspec["version"]}' for rname, rspec in lock_data['default'].items()
        if 'editable' not in rspec
    ]

setup(
        name='mystubs',
        version='0.1.0',
        description='Build mypy stubs for your dependencies',
        author='James Elford',
        author_email='james.p.elford@gmail.com',
        license='BSD 3-clause',
        install_requires=[
            'toml~=0.9.2',
            'mypy>=0.650',
            'appdirs~=1.4.3',
            'docopt~=0.6.2'
        ],
        packages=find_packages(),
        entry_points={
            'console_scripts': [
                'mystubs=mystubs.update:run',
            ]
        }
)

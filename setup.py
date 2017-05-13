from setuptools import setup, find_packages
from pip.req import parse_requirements

install_requires = [f'{ir.req}' for ir in parse_requirements('requirements.txt', session='hack')]

setup(
        name='mystubs',
        version='0.1.0',
        description='Build mypy stubs for your dependencies',
        author='James Elford',
        author_email='james.p.elford@gmail.com',
        license='BSD 3-clause',
        install_requires=install_requires,
        packages=find_packages(),
        entry_points={
            'console_scripts': [
                'mystubs=mystubs.update:run',
            ]
        }
)

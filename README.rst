mystubs
=======

A tool for managing local stubs for your python libraries. 

Many libraries choose not to ship their own type annotations, and don't appear
on the `typeshed <https://github.com/python/typeshed/>`_. ``mystubs`` will
autogenerate stubs for your dependencies, and allow you to specify overrides
when autogeneration doesn't do a good enough job.

installation
------------

``mystubs`` is not currently available on PyPI, as it's in an experimental state
and not ready for prime time.

::

    git clone https://github.com/jelford/mystubs.git
    pip install -e mystubs

usage
-----

``mystubs`` needs a simple configuration file:

::

    # /path/to/your/project/.mystubs.toml

    # For a simple project, this may be all you require
    discover_modules = true

For a simple project, this will be enough; you can now run:

::

    (localstubs) jelford@ ~/.c/m/localstubs> mystubs
    Building stubs for toml
    Building stubs for mypy
    Building stubs for appdirs
    Building stubs for docopt

All that remains is to let ``mypy`` know about your local stubs folder:

::

    set -x MYPYPATH .mystubs

Get commandline options with ``--help``:

::

    (localstubs) jelford@ ~/.c/m/localstubs> mystubs --help
    update.py

    Usage:
        update.py [--clean] [MODULE]

    Options:
        --clean     Remove all previous output

    Arguments:
        MODULE      Only generate or clean MODULE

options
-------

Options are configured in ``.mystubs.toml`` on a per-project basis.

``discover_modules``
  read in your ``requirements.txt`` and use that to decide which packages to generate stubs for

``modules.<module_name>``
  individual settings for each package

If ``discover_modules`` is false (or not present), then ``mystubs`` 
will determine packages by which ones have a configuration section.

e.g.

::

    # /path/to/your/project/.mystubs.toml

    # discover_modules = false

    [modules.toml]

``modules.<module_name>.version``
  tells ``mystubs`` what version of a module you are currently using. 
  Defaults to ``auto``: in this case it will be inferred from your 
  local ``requirements.txt``. This option is used to determine when stubs
  might need to be re-built.

``modules.<module_name>.package_name``
  tells ``mystubs`` that the name used for this module's root python package
  differs from its name used outside of python code (e.g. in ``requirements.txt``)
  An example of such a package is `progressbar2 <https://pypi.python.org/pypi/progressbar2>`_,
  which is called ``progressbar2`` on PyPI, but ``progressbar`` in source code.

your stubs
----------

The ideal outcome if for type annotations to be added directly to a project,
or failing that, contributed upstream to the ``typeshed``. ``mystubs`` is
useful when for some reason that's not possible.

Stubs are generated for each module with using the following strategy:

1. run ``stubgen`` across the module's root package and all its dependencies. 
   Outputs are put under ``.mystubs``
#. copy over any stubs from a user-local "third_party" typeshed.
#. copy over any project-local stubs, located under ``.mystubs/.local/<module_name>/``

Later stages overwrite outputs from previous stages.

user-local typeshed
-------------------

This repository of stubs is shared across all your projects, located under:

::
    
    ~/.config/mystubs/local     # linux
    %APP DATA%\mystubs\local    # Windows

It's structured as follows:

::

    (localstubs) jelford@ ~/.c/m/local> tree ~/.config/mystubs/local/
    /home/jelford/.config/mystubs/local/
    ├── 3                                # used for any python3 minor version
    │   └── docopt
    │       └── docopt.pyi
    └── 3.6                              # only for 3.6
        └── progressbar2                 # <module_name> as it appears in requirements.txt
            └── progressbar              # package name as it appears in python code
                ├── __init__.pyi
                └── six.pyi

Everything below ``<module_name>`` is copied directly into ``.mystubs`` when
a project configures ``mystubs`` to run for ``<module_name>`` (either explicitly
or through ``discover_modules = true``).

project-local typeshed
----------------------

These stubs are structured similarly, except that they are not broken down
by python version:

::

    (project) jelford@ ~/s/project> tree -a .mystubs/.local
    .mystubs/.local
    ├── docopt
    │   └── docopt.pyi
    ├── pexpect
    │   └── pexpect
    │       └── pty_spawn.pyi
    └── progressbar2
        └── progressbar
            ├── __init__.pyi
            └── six.pyi

It's intended that these stubs be checked into version control, as part of the
project, alongside other linting configuratons. As the final step in the stub
generation process, they give you complete control over what stubs ``mypy`` ends
up seeing for your project.

License
=======
Apache License 2: see `LICENSE <LICENSE>`_

Contributing
============
Please feel free to open up issues for any questions, feature requests, bug reports, ...

PRs are most welcome.
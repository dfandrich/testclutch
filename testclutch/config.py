"""Methods for retrieving the program configuration."""

import contextlib
import functools
import importlib.machinery
import importlib.util
import logging
import os
import sys
from types import ModuleType
from typing import Any

from testclutch import configdef


# Cache configuration module here
config_module = None

CONFIG_FILE = 'testclutchrc'

# Config variables that override all others
overrides = {}


def config_dir() -> str:
    """Get the directory in which to store the configuration files."""
    if 'XDG_CONFIG_HOME' in os.environ:
        return os.environ['XDG_CONFIG_HOME']
    if 'HOME' in os.environ:
        return os.path.join(os.environ['HOME'], '.config')
    return '.'


def persistent_dir() -> str:
    """Get the directory in which to store persistent data files."""
    if 'XDG_DATA_HOME' in os.environ:
        return os.environ['XDG_DATA_HOME']
    if 'HOME' in os.environ:
        return os.path.join(os.environ['HOME'], '.local', 'share')
    return '.'


def cache_dir() -> str:
    """Get the directory in which to store cache files."""
    if 'XDG_CACHE_HOME' in os.environ:
        return os.environ['XDG_CACHE_HOME']
    if 'HOME' in os.environ:
        return os.path.join(os.environ['HOME'], '.cache')
    return '.'


def environ() -> dict[str, str]:
    """Return a dict with the config environment.

    This contains the process environment variables, plus the default config variables,
    plus the local config variables, plus a few guaranteed variables
    The config variables all take precedence over the environment variables, so that an
    oddly-named environment variables doesn't override a configured value.

    See https://wiki.archlinux.org/title/XDG_Base_Directory for some standard vars.
    """
    env = {**os.environ, **configdef.__dict__, **config().__dict__, **overrides}
    if 'XDG_DATA_HOME' not in env:
        env['XDG_DATA_HOME'] = persistent_dir()
    if 'XDG_CONFIG_HOME' not in env:
        env['XDG_CONFIG_HOME'] = config_dir()
    if 'XDG_CACHE_HOME' not in env:
        env['XDG_CACHE_HOME'] = cache_dir()
    if 'USER' not in env and 'USERNAME' in env:
        env['USER'] = env['USERNAME']
    elif 'USER' not in env and 'LOGIN' in env:
        env['USER'] = env['LOGIN']
    elif 'USER' not in env:
        # This will error out if LOGNAME not found to avoid USER going undefined
        # LOGNAME is required by POSIX so this should never fail (on most systems)
        env['USER'] = env['LOGNAME']
    return env


def expandstr(var: str) -> str:
    """Expand a string with environment variables."""
    return var.format(**environ())


@functools.lru_cache(maxsize=None)
def expand(var: str) -> str:
    """Get a config variable and expand it with environment variables."""
    return expandstr(get(var))


@functools.lru_cache(maxsize=None)
def get(var: str) -> Any:
    """Get a raw config variable."""
    return environ()[var]


@contextlib.contextmanager
def override_var(obj, name: str, value: Any):
    """Change an object variable within a with context.

    The original value of the attribute is restore on context exit.

    Args:
        obj: reference to object
        name: name of the attribute to change
        value: new value to store in the attribute
    """
    saved_value = getattr(obj, name)
    setattr(obj, name, value)
    yield saved_value
    setattr(obj, name, saved_value)


def config() -> ModuleType:
    """Return the configuration file as a module."""
    global config_module
    if config_module:
        return config_module

    configfn = os.path.join(config_dir(), CONFIG_FILE)
    # There is a race condition here, but if the race fails, the only impact is a messier message
    if (os.access(configfn, os.R_OK)
        and (spec := importlib.util.spec_from_loader(
             'testclutchrc',
             importlib.machinery.SourceFileLoader(
                 'testclutchrc', configfn)))):
        config_module = importlib.util.module_from_spec(spec)

        # Don't write the imported config file bytecode file to eliminate caching problems
        with override_var(sys, 'dont_write_bytecode', True):
            spec.loader.exec_module(config_module)
    else:
        logging.info('Configuration file %s not found', configfn)
        config_module = ModuleType('empty')

    return config_module  # noqa: R504


def add_override(name: str, value: Any):
    """Add a config variable that overrides all others."""
    overrides[name] = value

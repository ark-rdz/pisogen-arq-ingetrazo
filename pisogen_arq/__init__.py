# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""PisoGen ARQ for IngeTrazo — floor generator (twenty compositions, joints,
bevels). © 2026 Alfonso Rodríguez.

IngeTrazo loads this package from its plugins folder and calls ``setup(app)``.
The geometry core (``pisogen_arq.core``) does not need IngeTrazo.
"""
__version__ = '2026.1.1'


def setup(app):
    from .ingetrazo.plugin import setup as install
    install(app)

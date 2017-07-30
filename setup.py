#!/usr/bin/env python
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os.path
import tempfile
import shutil
import glob

from distutils.command import install_data
from distutils.core import setup

from virtualbricks import __version__


class InstallData(install_data.install_data):

    def initialize_options(self):
        install_data.install_data.initialize_options(self)
        self.tmpdirs = []

    def compile_mo(self):
        for filename in glob.iglob("locale/virtualbricks/??.po"):
            lang, _ = os.path.basename(filename).split(".")
            tmpdir = tempfile.mkdtemp()
            self.tmpdirs.append(tmpdir)
            outfile = "{0}/virtualbricks.mo".format(tmpdir)
            self.spawn(["msgfmt", "-o", outfile, filename])
            self.data_files.append(
                ("share/locale/{0}/LC_MESSAGES".format(lang), [outfile])
            )

    def remove_temps(self):
        for tmpdir in self.tmpdirs:
            shutil.rmtree(tmpdir)

    def run(self):
        self.execute(self.compile_mo, ())
        install_data.install_data.run(self)
        self.execute(self.remove_temps, ())


data_images = glob.glob("virtualbricks/gui/data/*.png")
data_helps = glob.glob("virtualbricks/gui/data/help/*")
data_glade_ui = glob.glob("virtualbricks/gui/data/*.ui")


setup(
    name="virtualbricks",
    version=__version__,
    description="Virtualbricks Virtualization Tools",
    author="Daniele Lacamera, Rainer Haage, Francesco Apollonio, "
          "Pierre-Louis Bonicoli, Simone Abbati",
    author_email="qemulator-list@createweb.de",
    url="http://www.virtualbricks.eu/",
    license="GPLv2",
    platforms=["linux2", "linux"],
    packages=[
        "virtualbricks",
        "virtualbricks.gui",
        "virtualbricks.scripts",
        "virtualbricks.tests"
    ],
    package_data={"virtualbricks.tests": ["data/*"]},
    data_files=[
        ("share/applications", ["share/virtualbricks.desktop"]),
        ("share/pixmaps", ["share/virtualbricks.xpm"]),
        ("share/virtualbricks", data_images + data_glade_ui + data_helps),
    ],
    scripts=["bin/virtualbricks"],
    requires=["twisted (>=12.0.0)", "zope.interface (>=3.5)"],
    cmdclass={"install_data": InstallData}
)

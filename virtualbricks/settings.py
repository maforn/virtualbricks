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

import os
import ConfigParser

from virtualbricks import tools, _compat


if False:  # pyflakes
    _ = str


log = _compat.getLogger(__name__)


VDEPATH = "/usr/bin"
HOME = os.path.expanduser("~")
VIRTUALBRICKS_HOME = os.path.join(HOME, ".virtualbricks")
MYPATH = VIRTUALBRICKS_HOME  # backward compatibility
CONFIGFILE = os.path.join(HOME, ".virtualbricks.conf")
DEFAULT_PROJECT = os.path.join(VIRTUALBRICKS_HOME, "virtualbricks.vbl")
DEFAULT_CONF = {
    "term": "/usr/bin/xterm",
    "alt-term": "/usr/bin/gnome-terminal",
    "sudo": "/usr/bin/gksu",
    "qemupath": "/usr/bin",
    "baseimages": os.path.join(VIRTUALBRICKS_HOME, "img"),
    "kvm": False,
    "ksm": False,
    "kqemu": False,
    "cdroms": "",
    "vdepath": "/usr/bin",
    "python": False,
    "femaleplugs": False,
    "erroronloop": False,
    "systray": True,
    "current_project": DEFAULT_PROJECT,
    "cowfmt": "cow",
    "show_missing": True
}


class SettingsMeta(type):

    def __new__(cls, name, bases, dct):

        def make_property(opt):

            def get(self):
                return self.config.getboolean(self.DEFAULT_SECTION, opt)

            def set(self, val):
                return self.config.set(self.DEFAULT_SECTION, opt,
                                       bool(val))
            dct["get_" + opt] = get
            dct["set_" + opt] = set
            dct[opt] = property(get, set)

        for opt in dct["__boolean_values__"]:
            make_property(opt)

        return type.__new__(cls, name, bases, dct)


class SettingsBase:

    __metaclass__ = SettingsMeta
    __boolean_values__ = ()


class Settings(SettingsBase):

    __boolean_values__ = ('kvm', 'ksm', 'kqemu', 'python', 'femaleplugs',
                          'erroronloop', 'systray', 'show_missing')
    DEFAULT_SECTION = "Main"

    def __init__(self, filename):
        self.filename = filename
        self.config = ConfigParser.SafeConfigParser()
        self.config.add_section(self.DEFAULT_SECTION)
        for key, value in DEFAULT_CONF.items():
            self.config.set(self.DEFAULT_SECTION, key, str(value))

        if os.path.exists(self.filename):
            try:
                self.config.read(self.filename)
                log.info(_("Configuration loaded ('%s')"), self.filename)
            except ConfigParser.Error, e:
                log.error(_("Cannot read config file '%s': '%s'!"),
                          self.filename, e)
        else:
            log.info(_("Default configuration loaded"))
            try:
                with open(self.filename, "w") as fp:
                    self.config.write(fp)
                log.info(_("Default configuration saved ('%s')"),
                        self.filename)
            except IOError:
                log.error(_("Cannot save default configuration"))

        tools.enable_ksm(self.ksm, self.get("sudo"))

    def has_option(self, value):
        return self.config.has_option(self.DEFAULT_SECTION, value)

    def get(self, attr):
        if attr in self.__boolean_values__:
            return self.config.getboolean(self.DEFAULT_SECTION, attr)
        val = self.config.get(self.DEFAULT_SECTION, str(attr))
        if attr == 'sudo' and os.getuid() == 0:
            return ''
        return val

    def set(self, attr, value):
        self.config.set(self.DEFAULT_SECTION, attr, str(value))

    def store(self):
        with open(self.filename, "w") as fp:
            self.config.write(fp)

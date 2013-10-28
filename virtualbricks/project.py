# -*- test-case-name: virtualbricks.tests.test_project -*-
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
import errno
import itertools
import re

from twisted.internet import utils, error, defer
from twisted.python import filepath

from virtualbricks import (settings, configfile, log, errors, configparser,
                           tools)


logger = log.Logger()
__metaclass__ = type

create_archive = log.Event("Create archive in {path}")
extract_archive = log.Event("Extract archive in {path}")
restore_project = log.Event("Restoring project {name}")
import_project = log.Event("Importing project from {path} as {name}")
create_project = log.Event("Create project {name}")
write_project = log.Event("Writing new .project file")
rebase_error = log.Event("Error on rebase")
rebase = log.Event("Rebasing {cow} to {basefile}")
remap_image = log.Event("Mapping {original} to {new}")
extract_project = log.Event("Extracting project")
cannot_find_project = log.Event("Cannot find project \"{name}\". "
                                "A new project will be created.")
include_images = log.Event("Including the following images to the project: "
                           "{images}.")
save_images = log.Event("Move virtual machine's images")
DEFAULT_PROJECT_RE = re.compile(r"^{0}(?:_\d+)?$".format(
    settings.DEFAULT_PROJECT))


def _complain_on_error(result):
    out, err, code = result
    if code != 0:
        logger.warn(err)
        raise error.ProcessTerminated(code)
    logger.info(err)
    return result


class Tgz:

    exe_c = exe_x = "tar"

    def create(self, pathname, files, images=(),
               run=utils.getProcessOutputAndValue):
        logger.info(create_archive, path=pathname)
        args = ["cfzh", pathname, "-C", settings.VIRTUALBRICKS_HOME] + files
        if images:
            logger.info(include_images, images=images)
            prjpath = filepath.FilePath(settings.VIRTUALBRICKS_HOME)
            imgs = prjpath.child(".images")
            try:
                imgs.remove()
            except OSError as e:
                if e.errno != errno.ENOENT:
                    return defer.fail(e)
            imgs.makedirs()
            for name, image in images:
                fp = filepath.FilePath(image)
                if fp.exists():
                    link = imgs.child(name)
                    fp.linkTo(link)
                    args.append("/".join(link.segmentsFrom(prjpath)))
        d = run(self.exe_c, args, os.environ)
        d.addCallback(_complain_on_error)
        if images:
            d.addBoth(pass_through(imgs.remove))
        return d

    def extract(self, pathname, destination,
                run=utils.getProcessOutputAndValue):
        logger.info(extract_archive, path=destination)
        args = ["Sxfz", pathname, "-C", destination]
        d = run(self.exe_x, args, os.environ)
        return d.addCallback(_complain_on_error)


class BsdTgz(Tgz):

    exe_c = exe_x = "bsdtar"


class ProjectEntry:

    def __init__(self, sections, links):
        self.sections = sections
        self.links = links

    @classmethod
    def from_fileobj(cls, fileobj):
        links = []
        sections = {}
        for item in configparser.Parser(fileobj):
            if isinstance(item, tuple):
                links.append(item)
            else:
                sections[(item.type, item.name)] = dict(item)
        return cls(sections, links)

    def _filter(self, fltr):
        return [(s, self.sections[s]) for s in self.sections if fltr(s)]

    def has_image(self, name):
        return ("Image", name) in self.sections

    def get_images(self):
        return self._filter(lambda k: k[0] == "Image")

    def remap_image(self, name, path):
        if self.has_image(name):
            self.sections[("Image", name)]["path"] = path

    def get_bricks(self):
        bricks = set(["Qemu", "Switch", "SwitchWrapper", "Tap", "Capture",
                      "Wirefilter", "Wire", "TunnelConnect", "TunnelListen",
                      "Router"])
        return self._filter(lambda k: k[0] in bricks)

    def get_events(self):
        return self._filter(lambda k: k[0] == "Event")

    def get_virtualmachines(self):
        return self._filter(lambda k: k[0] == "Qemu")

    def get_disks(self):
        disks = {}
        for header, section in self.get_virtualmachines():
            for dev in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
                if dev in section:
                    disks.setdefault(header[1], []).append((dev, section[dev]))
        return disks

    def device_for_image(self, name):
        for (typ, vmname), section in self.get_virtualmachines():
            for dev in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
                if dev in section and section[dev] == name:
                    yield vmname, dev

    def _dump_section(self, fileobj, header, section):
        fileobj.write("[{0[0]}:{0[1]}]\n".format(header))
        for name in section:
            fileobj.write("{0} = {1}\n".format(name, section[name]))
        fileobj.write("\n")

    def dump(self, fileobj):
        for header, section in self.get_images():
            self._dump_section(fileobj, header, section)
        for header, section in self.get_events():
            self._dump_section(fileobj, header, section)
        for header, section in self.get_bricks():
            self._dump_section(fileobj, header, section)
        for link in self.links:
            fileobj.write("{0}\n".format("|".join(link)))


def pass_through(function, *args, **kwds):
    def wrapper(arg):
        function(*args, **kwds)
        return arg
    return wrapper


class ProjectManager:

    archive = BsdTgz()


    def __iter__(self):
        path = self.workspace()
        return (p.basename() for p in path.children() if
                p.child(".project").isfile())

    def project_path(self, name):
        try:
            return self.workspace().child(name)
        except filepath.InsecurePath:
            raise errors.InvalidNameError(name)

    def workspace(self):
        return filepath.FilePath(settings.get("workspace"))

    def exists(self, name):
        # return self.project_path(name).exists()
        try:
            prj = self.create(name)
            prj.delete()
            return False
        except errors.ProjectExistsError:
            return True

    def open(self, name, factory):
        fp = self.project_path(name)
        try:
            prj = Project(fp)
            prj.restore(factory)
            return prj
        except EnvironmentError as e:
            if e.errno in (errno.ENOENT, errno.ENOTDIR):
                raise errors.ProjectNotExistsError(name)

    def create(self, name, overwrite=False):
        project = Project(self.project_path(name))
        try:
            project.filepath.makedirs()
        except OSError as e:
            if e.errno == errno.EEXIST:
                if overwrite:
                    self.delete(name)
                    return self.create(name)
                raise errors.ProjectExistsError(name)
            else:
                raise
        else:
            project.filepath.child(".project").touch()
            logger.debug(create_project, name=name)
            return project

    def close(self, factory):
        factory.reset()
        global current
        if current:
            current = None
            settings.VIRTUALBRICKS_HOME = settings.DEFAULT_HOME

    def export(self, output, files, images=()):
        return self.archive.create(output, files, images)

    def delete(self, name):
        fp = self.project_path(name)
        try:
            fp.remove()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def extract(self, name, vbppath):
        try:
            project = self.create(name)
        except Exception as e:
            return defer.fail(e)
        logger.debug(extract_project)
        deferred = self.archive.extract(vbppath, project.filepath.path)
        return deferred.addCallback(lambda _: project)


manager = ProjectManager()
current = None


class Project:

    manager = manager

    def __init__(self, path):
        self.filepath = path

    @property
    def path(self):
        return self.filepath.path

    @property
    def name(self):
        return self.filepath.basename()

    def restore(self, factory):
        logger.debug(restore_project, name=self.name)
        self.manager.close(factory)
        global current
        current = self
        settings.set("current_project", self.name)
        settings.VIRTUALBRICKS_HOME = self.path
        settings.store()
        configfile.restore(factory, self.dot_project().path)

    def save(self, factory):
        configfile.save(factory, self.dot_project().path)

    def save_as(self, name, factory):
        self.save(factory)
        dst = self.filepath.sibling(name)
        tools.copyTo(self.filepath, dst)

    def rename(self, name, overwrite=False):
        new = self.manager.create(name, overwrite)
        new.filepath.remove()
        self.filepath.moveTo(new.filepath)
        self.filepath = new.filepath

    def delete(self):
        self.manager.delete(self.name)

    def files(self):
        return (fp for fp in self.filepath.walk() if fp.isfile())

    def dot_project(self):
        return self.filepath.child(".project")

    def imported_images(self):
        path = self.filepath.child(".images")
        if path.isdir():
            return path.children()
        return []

    def get_descriptor(self):
        with self.dot_project().open() as fp:
            return ProjectEntry.from_fileobj(fp)


def restore_last_project(factory):
    """Restore the last project if found or create a new one."""

    try:
        os.makedirs(os.path.join(settings.get("workspace"), "vimages"))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    name = settings.get("current_project")
    try:
        return manager.open(name, factory)
    except errors.ProjectNotExistsError:
        if DEFAULT_PROJECT_RE.match(name):
            prj = manager.create(name)
            prj.restore(factory)
            return prj
        else:
            logger.error(cannot_find_project, name=name)
            for i in itertools.count():
                name = "{0}_{1}".format(settings.DEFAULT_PROJECT, i)
                try:
                    prj = manager.create(name)
                    prj.restore(factory)
                    return prj
                except errors.ProjectExistsError:
                    pass


restore_last = restore_last_project

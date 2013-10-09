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
import tarfile
import itertools
import re

from twisted.internet import utils, error, defer
from twisted.python import filepath

from virtualbricks import settings, configfile, log, errors, configparser


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


class BsdTgz:

    exe_c = exe_x = "bsdtar"

    def create(self, pathname, files, images=(),
               run=utils.getProcessOutputAndValue):
        logger.info(create_archive, path=pathname)
        args = ["cfzh", pathname]
        images_args = []
        if images:
            logger.info(include_images, images=images)
            parts = []
            for dirname, basename in map(os.path.split, images):
                images_args.extend(("-C", dirname, basename))
                parts.append(basename)
            pattern = r"/^\({0}\)$/.image.\1/".format(r"\|".join(parts))
            args.extend(("-s", pattern))
        args.extend(["-C", settings.VIRTUALBRICKS_HOME])
        args.extend(files)
        args.extend(images_args)
        d = run(self.exe_c, args, os.environ)
        d.addCallback(_complain_on_error)
        return d

    def extract(self, pathname, destination,
                run=utils.getProcessOutputAndValue):
        logger.info(extract_archive, path=destination)
        args = ["Sxfz", pathname, "-C", destination]
        d = run(self.exe_x, args, os.environ)
        return d.addCallback(_complain_on_error)


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


class Archive:

    def __init__(self, filename):
        self.archive = tarfile.open(filename)

    def get_member(self, name):
        return self.archive.getmember(name)

    def get_project(self):
        project = self.archive.getmember(".project")
        return ProjectEntry.from_fileobj(self.archive.extractfile(project))


def pass_through(function, *args, **kwds):
    def wrapper(arg):
        function(*args, **kwds)
        return arg
    return wrapper


class ProjectManager:

    archive = BsdTgz()

    def __iter__(self):
        path = filepath.FilePath(settings.get("workspace"))
        return (p.basename() for p in path.children() if
                p.child(".project").isfile())

    def project_path(self, name):
        workspace = filepath.FilePath(settings.get("workspace"))
        try:
            return workspace.child(name)
        except filepath.InsecurePath:
            raise errors.InvalidNameError(name)

    def exists(self, name):
        path = filepath.FilePath(settings.get("workspace"))
        return path.child(name).exists()

    def open(self, name, factory):
        fp = self.project_path(name)
        try:
            return self.restore(Project(fp), factory)
        except EnvironmentError as e:
            if e.errno in (errno.ENOENT, errno.ENOTDIR):
                raise errors.ProjectNotExistsError(name)

    def restore(self, project, factory):
        logger.debug(restore_project, name=project.name)
        self.close(factory)
        global current
        current = project
        settings.set("current_project", project.name)
        settings.VIRTUALBRICKS_HOME = project.path
        settings.store()
        project.restore(factory)
        return project

    def create(self, name, factory, open=True):
        project = Project(self.project_path(name))
        try:
            project.filepath.makedirs()
        except OSError as e:
            if e.errno == errno.EEXIST:
                raise errors.ProjectExistsError(name)
            else:
                raise
        else:
            project.filepath.child(".project").touch()
            logger.debug(create_project, name=name)
            if open:
                return self.restore(project, factory)
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

    def import2(self, name, vbppath, factory, map_cb, open=True):
        try:
            project = self.create(name, factory, False)
        except:
            return defer.fail()
        deferred = self.__extract(vbppath, project.filepath.path)
        deferred.addCallback(self.__map_images, map_cb, project)
        deferred.addCallback(lambda _: project)
        deferred.addErrback(pass_through(self.delete, name))
        if open:
            deferred.addCallback(self.restore, factory)
        return deferred

    def __extract(self, vbpname, path):
        logger.debug(extract_project)
        return self.archive.extract(vbpname, path)

    def __map_images(self, _, map_cb, project):
        with project.dot_project().open() as fp:
            entry = ProjectEntry.from_fileobj(fp)
        d = map_cb(entry.get_images())
        return d.addCallback(self.__rebase, entry, project)

    def __rebase(self, new_map, prjentry, project):
        if new_map:
            self.__save_dot_project(new_map, prjentry, project.dot_project())
            dl = []
            for name, path in filter(lambda e: bool(e[1]), new_map):
                for vmname, dev in prjentry.device_for_image(name):
                    cow_name = "{0}_{1}.cow".format(vmname, dev)
                    cow = project.filepath.child(cow_name)
                    if cow.exists():
                        logger.debug(rebase, cow=cow.path, basefile=path)
                        dl.append(self._real_rebase(path, cow.path))
            return defer.DeferredList(dl).addCallback(self.__check_rebase)

    def __save_dot_project(self, new_map, prjentry, dot_project):
        for name, path in new_map:
            logger.debug(remap_image, original=name, new=path)
            prjentry.remap_image(name, path)
        logger.debug(write_project)
        with dot_project.open("w") as fp:
            prjentry.dump(fp)

    def __check_rebase(self, result):
        for success, status in result:
            if not success:
                logger.error(rebase_error, log_failure=status)

    def import_(self, prjname, path, factory, image_mapper, open=True):
        """Import a project in the current workspace.

        @param prjname: name of the new project.
        @param path: the path of the .vbp file.
        @param factory: the brick factory.
        @param image_mapper: a callable that accept a list of images and return
            a dictionary. Keys are the name of the images and values are the
            new paths.
        @param open: If True the project will be open after the import.
        """

        logger.debug(import_project, path=path, name=prjname)
        try:
            prjentry = Archive(path).get_project()
        except KeyError:
            raise errors.InvalidArchiveError(".project file not found.")
        except tarfile.TarError as e:
            raise errors.InvalidArchiveError(*e.args)
        deferred = defer.maybeDeferred(image_mapper, prjentry.get_images())
        deferred.addCallback(self._import_cb, prjname, path, factory, prjentry)
        if open:
            deferred.addCallback(self.restore, factory)
        deferred.addErrback(self._import_eb, prjname)
        return deferred

    def _import_eb(self, fail, prjname):
        self.delete(prjname)
        return fail

    def _import_cb(self, dct, name, path, factory, prjentry):
        self._remap_images(dct, prjentry)
        prj = self.create(name, factory, False)
        return self._extract(prj, prjentry, path, dct)

    def _remap_images(self, dct, prjentry):
        for name, path in dct.iteritems():
            if prjentry.has_image(name):
                logger.debug(remap_image, original=name, new=path)
                prjentry.remap_image(name, path)

    def _extract(self, project, prjentry, pathname, dct):
        logger.debug(extract_project)
        deferred = self.archive.extract(pathname, project.path)
        return deferred.addCallback(self._rebase, project, prjentry, dct)

    def _rebase(self, _, project, prjentry, dct):
        logger.debug(write_project)
        with project.filepath.child(".project").open("w") as fp:
            prjentry.dump(fp)
        return self._rebase_cb(project, prjentry, dct)

    def _rebase_cb(self, project, prjentry, dct):
        def check_rebase(result):
            for success, status in result:
                if not success:
                    logger.error(rebase_error, log_failure=status)
            return project

        disks = prjentry.get_disks()
        images = dict(prjentry.get_images())
        dl = []
        for vmname in disks:
            for dev, iname in disks[vmname]:
                cow = project.filepath.child("{0}_{1}.cow".format(vmname, dev))
                if cow.exists() and ("Image", iname) in images:
                    backing_file = images[("Image", iname)]["path"]
                    logger.debug(rebase, cow=cow.path, basefile=backing_file)
                    dl.append(self._real_rebase(backing_file, cow.path))
        return defer.DeferredList(dl).addCallback(check_rebase)

    def _real_rebase(self, backing_file, cow):
        args = ["rebase", "-u", "-b", backing_file, cow]
        d = utils.getProcessOutputAndValue("qemu-img", args, os.environ)
        d.addCallback(_complain_on_error)
        return d


manager = ProjectManager()
current = None


class Project:

    def __init__(self, path):
        self.filepath = path

    @property
    def path(self):
        return self.filepath.path

    @property
    def name(self):
        return self.filepath.basename()

    def restore(self, factory):
        configfile.restore(factory, self.dot_project().path)

    def save(self, factory):
        configfile.save(factory, self.dot_project().path)

    def files(self):
        return (fp for fp in self.filepath.walk() if fp.isfile())

    def dot_project(self):
        return self.filepath.child(".project")


def restore_last_project(factory):
    """Restore the last project if found or create a new one."""

    try:
        os.mkdir(settings.get("workspace"))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    name = settings.get("current_project")
    try:
        return manager.open(name, factory)
    except errors.ProjectNotExistsError:
        if DEFAULT_PROJECT_RE.match(name):
            return manager.create(name, factory, open=True)
        else:
            logger.error(cannot_find_project, name=name)
            for i in itertools.count():
                name = "{0}_{1}".format(settings.DEFAULT_PROJECT, i)
                try:
                    return manager.create(name, factory, open=True)
                except errors.ProjectExistsError:
                    pass


restore_last = restore_last_project

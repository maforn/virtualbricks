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
import time
import logging
import subprocess

import gtk
from zope.interface import implements

from virtualbricks import (interfaces, base, bricks, events, virtualmachines,
                           console, link)

from virtualbricks.gui import graphics, dialogs


log = logging.getLogger("virtualbricks.gui.gui")

if False:  # pyflakes
    _ = str


class BaseMenu:
    implements(interfaces.IMenu)

    def __init__(self, brick):
        self.original = brick

    def build(self, gui):
        menu = gtk.Menu()
        menu.append(gtk.MenuItem(self.original.get_name(), False))
        menu.append(gtk.SeparatorMenuItem())
        start_stop = gtk.MenuItem("_Start/Stop")
        start_stop.connect("activate", self.on_startstop_activate, gui)
        menu.append(start_stop)
        delete = gtk.MenuItem("_Delete")
        delete.connect("activate", self.on_delete_activate, gui)
        menu.append(delete)
        copy = gtk.MenuItem("Make a C_opy")
        copy.connect("activate", self.on_copy_activate, gui)
        menu.append(copy)
        rename = gtk.MenuItem("Re_name")
        rename.connect("activate", self.on_rename_activate, gui)
        menu.append(rename)
        configure = gtk.MenuItem("_Configure")
        configure.connect("activate", self.on_configure_activate, gui)
        menu.append(configure)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    def on_configure_activate(self, menuitem, gui):
        gui.curtain_up(self.original)
        gui.curtain_is_down = False


class BrickPopupMenu(BaseMenu):

    def build(self, gui):
        menu = BaseMenu.build(self, gui)
        attach = gtk.MenuItem("_Attach Event")
        attach.connect("activate", self.on_attach_activate, gui)
        menu.append(attach)
        return menu

    def on_startstop_activate(self, menuitem, gui):
        gui.user_wait_action(gui.startstop_brick, self.original)

    def on_delete_activate(self, menuitem, gui):
        message = ""
        if self.original.proc is not None:
            message = _("The brick is still running, it will be killed before being deleted!\n")
        gui.ask_confirm(message + _("Do you really want to delete %s %s?") % (
            self.original.get_type(), self.original.get_name()),
            on_yes=gui.brickfactory.delbrick, arg=self.original)

    def on_copy_activate(self, menuitem, gui):
        gui.brickfactory.dupbrick(self.original)

    def on_rename_activate(self, menuitem, gui):
        if self.original.proc is not None:
            log.error(_("Cannot rename Brick: it is in use."))
        else:
            gui.gladefile.get_widget('entry_brick_newname').set_text(
                self.original.get_name())
            gui.gladefile.get_widget('dialog_rename').show_all()

    def on_attach_activate(self, menuitem, gui):
        gui.on_brick_attach_event(menuitem)

interfaces.registerAdapter(BrickPopupMenu, bricks.Brick, interfaces.IMenu)


# NOTE: there is a problem with this approach, it is not transparent, it must
# know the type of the brick, however virtual machines are already not
# transparent to the gui
class GVirtualMachine(virtualmachines.VirtualMachine):

    def has_graphic(self):
        return self.homehost is None


class VMPopupMenu(BrickPopupMenu):

    def build(self, gui):
        menu = BrickPopupMenu.build(self, gui)
        resume = gtk.MenuItem("_Resume VM")
        resume.connect("activate", self.on_resume_activate, gui)
        menu.append(resume)
        return menu

    def on_resume_activate(self, menuitem, gui):
        hda = self.original.cfg.get('basehda')
        log.debug("Resuming virtual machine %s", self.original.get_name())
        if os.system("qemu-img snapshot -l " + hda + " |grep virtualbricks") == 0:
            if self.original.proc is not None:
                self.original.send("loadvm virtualbricks\n")
                self.original.recv()
            else:
                self.original.cfg["loadvm"] = "virtualbricks"
                self.original.poweron()
        else:
            log.error(_("Cannot find suspend point."))


interfaces.registerAdapter(VMPopupMenu, GVirtualMachine, interfaces.IMenu)


class EventPopupMenu(BaseMenu):

    def on_startstop_activate(self, menuitem, gui):
        gui.user_wait_action(gui.event_startstop_brick, self.original)

    def on_delete_activate(self, menuitem, gui):
        message = ""
        if self.original.active:
            message = _("This event is in use") + ". "
        gui.ask_confirm(message + _("Do you really want to delete %s %s?") % (
            self.original.get_type(), self.original.get_name()),
            on_yes=gui.brickfactory.delevent, arg=self.original)

    def on_copy_activate(self, menuitem, gui):
        gui.brickfactory.dupevent(self.original)

    def on_rename_activate(self, menuitem, gui):
        gui.gladefile.get_widget('entry_event_newname').set_text(
            self.original.get_name())
        gui.gladefile.get_widget('dialog_event_rename').show_all()


interfaces.registerAdapter(EventPopupMenu, events.Event, interfaces.IMenu)


class RemoteHostPopupMenu:
    implements(interfaces.IMenu)

    def __init__(self, original):
        self.original = original

    def build(self, gui):
        menu = gtk.Menu()
        label = _("Disconnect") if self.original.connected else _("Connect")
        connect = gtk.MenuItem(label)
        connect.connect("activate", self.on_connect_activate, gui)
        menu.append(connect)
        change_pw = gtk.MenuItem("Change password")
        change_pw.connect("activate", self.on_change_password_activate, gui)
        menu.append(change_pw)
        ac = gtk.CheckMenuItem("Auto-connect at startup")
        ac.set_active(self.original.autoconnect)
        ac.connect("activate", self.on_ac_activate, gui)
        menu.append(ac)
        delete = gtk.MenuItem("Delete")
        delete.connect("activate", self.on_delete_activate, gui)
        menu.append(delete)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    def on_connect_activate(self, menuitem, gui):
        if self.original.connected:
            self.original.disconnect()
        else:
            # XXX: this will block
            conn_ok, msg = self.original.connect()
            if not conn_ok:
                log.error("Error connecting to remote host %s: %s",
                    self.original.addr[0], msg)

    def on_change_password_activate(self, menuitem, gui):
        dialogs.ChangePasswordDialog(self.original).show()

    def on_ac_activate(self, menuitem, gui):
        self.original.autoconnect = menuitem.get_active()

    def on_delete_activate(self, menuitem, gui):
        gui.ask_confirm(_("Do you really want to delete remote host ") +
            " \"" + self.original.addr[0] + "\" and all the bricks related?",
            on_yes=gui.brickfactory.delremote, arg=self.original)


interfaces.registerAdapter(RemoteHostPopupMenu, console.RemoteHost,
                           interfaces.IMenu)


class LinkMenu:
    implements(interfaces.IMenu)

    def __init__(self, original):
        self.original = original

    def build(self, gui):
        menu = gtk.Menu()
        edit = gtk.MenuItem(_("Edit"))
        edit.connect("activate", self.on_edit_activate, gui)
        menu.append(edit)
        remove = gtk.MenuItem(_("Remove"))
        remove.connect("activate", self.on_remove_activate, gui)
        menu.append(remove)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    def on_edit_activate(self, menuitem, gui):
        dialog = dialogs.EthernetDialog(gui, self.original.brick,
                                  self.original)
        dialog.window.set_transient_for(gui.widg["main_win"])
        dialog.show()

    def on_remove_activate(self, menuitem, gui):
        question = _("Do you really want to delete eth%d network interface") \
                % self.original.vlan
        dialog = dialogs.ConfirmDialog(question, on_yes=gui.remove_link,
                                       on_yes_arg=self.original)
        dialog.window.set_transient_for(gui.widg["main_win"])
        dialog.show()

interfaces.registerAdapter(LinkMenu, link.Plug, interfaces.IMenu)
interfaces.registerAdapter(LinkMenu, link.Sock, interfaces.IMenu)


class JobMenu:
    implements(interfaces.IMenu)

    def __init__(self, original):
        self.original = original

    def build(self, gui):
        menu = gtk.Menu()
        open = gtk.MenuItem(_("Open control monitor"))
        open.connect("activate", self.on_open_activate)
        menu.append(open)
        menu.append(gtk.SeparatorMenuItem())
        stop = gtk.ImageMenuItem(gtk.STOCK_STOP)
        stop.connect("activate", self.on_stop_activate)
        menu.append(stop)
        cont = gtk.ImageMenuItem(gtk.STOCK_MEDIA_PLAY)
        cont.set_label(_("Continue"))
        cont.connect("activate", self.on_cont_activate)
        menu.append(cont)
        menu.append(gtk.SeparatorMenuItem())
        reset = gtk.ImageMenuItem(gtk.STOCK_REDO)
        reset.set_label(_("Restart"))
        reset.connect("activate", self.on_reset_activate)
        menu.append(reset)
        kill = gtk.ImageMenuItem(gtk.STOCK_DELETE)
        kill.set_label(_("Kill"))
        kill.connect("activate", self.on_kill_activate)
        menu.append(kill)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    def on_open_activate(self, menuitem):
        self.original.open_console()

    def on_stop_activate(self, menuitem):
        log.debug("Sending to process signal 19!")
        self.original.proc.send_signal(19)

    def on_cont_activate(self, menuitem):
        log.debug("Sending to process signal 18!")
        self.original.proc.send_signal(18)

    def on_reset_activate(self, menuitem):
        log.debug("Restarting process!")
        self.original.poweroff()
        self.original.poweron()

    def on_kill_activate(self, menuitem):
        log.debug("Sending to process signal 9!")
        self.original.proc.send_signal(9)


interfaces.registerAdapter(JobMenu, bricks.Brick, interfaces.IJobMenu)


class VMJobMenu(JobMenu):

    def build(self, gui):
        menu = JobMenu.build(self, gui)
        suspend = gtk.MenuItem(_("Suspend virtual machine"))
        suspend.connect("activate", self.on_suspend_activate)
        menu.insert(suspend, 5)
        powerdown = gtk.MenuItem(_("Send ACPI powerdown"))
        powerdown.connect("activate", self.on_powerdown_activate)
        menu.insert(powerdown, 6)
        reset = gtk.MenuItem(_("Send ACPI hard reset"))
        reset.connect("activate", self.on_reset_activate)
        menu.insert(reset, 7)
        menu.insert(gtk.SeparatorMenuItem(), 8)
        return menu

    def on_suspend_activate(self, menuitem):
        hda = self.original.cfg["basehda"]
        if hda is None or 0 != subprocess.Popen(["qemu-img", "snapsho", "-c",
                                           "virtualbricks",hda]).wait():
            log.error(_("Suspend/Resume not supported on this disk."))
            return
        self.original.recv()
        self.original.send("savevm virtualbricks\n")
        while not self.original.recv().startswith("(qemu"):
            time.sleep(0.5)
        self.original.poweroff()

    def on_powerdown_activate(self, menuitem):
        log.info("send ACPI powerdown")
        self.original.send("system_powerdown\n")
        self.original.recv()

    def on_reset_activate(self, menuitem):
        log.info("send ACPI reset")
        self.original.send("system_reset\n")
        self.original.recv()


interfaces.registerAdapter(VMJobMenu, GVirtualMachine, interfaces.IJobMenu)


class ConfigController(object):
    implements(interfaces.IConfigController)

    domain = "virtualbricks"
    resource = None

    def __init__(self, original):
        self.original = original
        self.builder = builder = gtk.Builder()
        builder.set_translation_domain(self.domain)
        builder.add_from_file(graphics.get_filename("virtualbricks.gui",
                                                    self.resource))
        builder.connect_signals(self)

    def get_object(self, name):
        return self.builder.get_object(name)

# class EventConfigController(ConfigController):

#     resource = "data/event_configuration.ui"


class SwitchConfigController(ConfigController):

    resource = "data/switchconfig.ui"

    def get_view(self, gui):
        self.get_object("fstp_checkbutton").set_active(
            self.original.cfg["fstp"])
        self.get_object("hub_checkbutton").set_active(self.original.cfg["hub"])
        minports = len([1 for b in iter(gui.brickfactory.bricks)
                        for p in b.plugs if b.socks
                        and p.sock.nickname == b.socks[0].nickname])
        spinner = self.get_object("ports_spinbutton")
        spinner.set_range(max(minports, 1), 128)
        spinner.set_value(int(self.original.cfg.numports))
        return self.get_object("table")

    def configure_brick(self, gui):
        self.original.cfg["fstp"] = self.get_object(
            "fstp_checkbutton").get_active()
        self.original.cfg["hub"] = self.get_object(
            "hub_checkbutton").get_active()
        self.original.cfg["numports"] = \
                self.get_object("ports_spinbutton").get_value_as_int()


def should_insert_sock(sock, brick, python, femaleplugs):
    return ((sock.brick.homehost == brick.homehost or
             (brick.get_type() == 'Wire' and python)) and
            (sock.brick.get_type().startswith('Switch') or femaleplugs))


class TapConfigController(ConfigController):

    resource = "data/tapconfig.ui"

    def get_view(self, gui):
        self.get_object("ip_entry").set_text(self.original.cfg["ip"])
        self.get_object("nm_entry").set_text(self.original.cfg["nm"])
        self.get_object("gw_entry").set_text(self.original.cfg["gw"])
        # default to manual if not valid mode is set
        if self.original.cfg["mode"] == "off":
            self.get_object("nocfg_radiobutton").set_active(True)
        elif self.original.cfg["mode"] == "dhcp":
            self.get_object("dhcp_radiobutton").set_active(True)
        else:
            self.get_object("manual_radiobutton").set_active(True)
        self.get_object("ipconfig_table").set_sensitive(
            self.original.cfg["mode"] == "manual")
        combo = self.get_object("sockscombo_tap")
        model = combo.get_model()
        model.clear()  # XXX: needed?
        for i, sock in enumerate(iter(gui.brickfactory.socks)):
            if should_insert_sock(sock, self.original, gui.config.python,
                    gui.config.femaleplugs):
                model.append((sock.nickname, ))
                if (self.original.plugs[0].configured() and
                        self.original.plugs[0].sock.nickname == sock.nickname):
                    combo.set_active(i)
        return self.get_object("vbox")

    def configure_brick(self, gui):
        model = self.get_object("sockscombo_tap").get_model()
        itr = self.get_object("sockscombo_tap").get_active_iter()
        if itr:
            sel = model.get_value(itr, 0)
            for sock in iter(gui.brickfactory.socks):
                if sel == sock.nickname:
                    self.original.plugs[0].connect(sock)
        if self.get_object("nocfg_radiobutton").get_active():
            self.original.cfg["mode"] = "off"
        elif self.get_object("dhcp_radiobutton").get_active():
            self.original.cfg["mode"] = "dhcp"
        else:
            self.original.cfg["mode"] = "manual"
            self.original.cfg["ip"] = self.get_object("ip_entry").get_text()
            self.original.cfg["nm"] = self.get_object("nm_entry").get_text()
            self.original.cfg["gw"] = self.get_object("gw_entry").get_text()

    def on_manual_radiobutton_toggled(self, radiobtn):
        self.get_object("ipconfig_table").set_sensitive(radiobtn.get_active())


def config_panel_factory(context):
    type = context.get_type()
    # if type == "Event":
    #     return EventConfigController(context)
    if type == "Switch":
        return SwitchConfigController(context)
    elif type == "Tap":
        return TapConfigController(context)


interfaces.registerAdapter(config_panel_factory, base.Base,
                           interfaces.IConfigController)

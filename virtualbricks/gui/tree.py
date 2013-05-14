# -*- test-case-name: virtualbricks.tests.test_tree -*-
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

import gtk

from virtualbricks.gui import graphics


if False:  # pyflakes
	_ = str


class VBTree:

	def __init__(self, gui, tree_name, model, fields, names):
		self.gui = gui
		self.tree = self.gui.gladefile.get_widget(tree_name)
		self.last_order = 0
		self.order_last_direction = True
		self.last_known_selection = None
		self.fields = fields
		self.names = names
		if model:
			self.model = model
			self.tree.set_model(self.model)
		else:
			self.model = gtk.TreeStore(*fields)
			self.tree.set_model(self.model)

		for idx, name in enumerate(names):
			col = gtk.TreeViewColumn(name)
			if fields[idx] == gtk.gdk.Pixbuf:
				elem = gtk.CellRendererPixbuf()
				col.pack_start(elem, False)
				if model is None:
					col.add_attribute(elem, 'pixbuf', idx)
			else:
	 			elem = gtk.CellRendererText()
				col.pack_start(elem, False)
				if model is None:
					col.add_attribute(elem, 'text', idx)
			if model is not None:
				col.set_cell_data_func(elem, self.cell_render)
			col.set_clickable(True)
			col.connect("clicked",self.header_clicked)
			self.tree.append_column(col)

	def set_value(self, itr, col, val):
		return self.model.set_value(itr, col, val)

	''' Override me, so I know how to order the objects '''
	def _treeorder_continue(self, itr, field, asc, moved = False):
		if itr is None:
			return moved
		nxt = self.model.iter_next(itr)
		if (nxt):
			val_itr = self.model.get_value(itr, field)
			val_nxt = self.model.get_value(nxt, field)
			if asc:
				if val_nxt <  val_itr:
					self.model.swap(itr,nxt)
					moved = True
			else:
				if val_nxt >  val_itr:
					self.model.swap(itr,nxt)
					moved = True

			return self._treeorder_continue(nxt, field, asc, moved)
		else:
			return moved

	def header_clicked(self, widget, event=None, data=""):
		return self.order_header_clicked(widget, event, data)

	def get_column_from_fieldname(self, name):
		column = -1
		for i,n in enumerate(self.names):
			if n == name:
				column = i
				break
		return column


	def order_header_clicked(self, widget, event, data):
		column = widget.get_title()
		direction = True
		if column == self.last_order:
			direction = not self.order_last_direction
		self.order(column, direction)

	def order(self, field=None, ascending=True):
		if field is None:
			field = _("Type")
		self.order_last_direction = ascending
		field = self.get_column_from_fieldname(field)
		self.last_order = field
		itr = self.model.get_iter_first()
		if self.fields[field] == gtk.gdk.Pixbuf:
			return
		moved = self._treeorder_continue(itr, field, ascending)
		while moved:
			itr = self.model.get_iter_first()
			moved = self._treeorder_continue( itr, field, ascending)

	def get_selection(self, path=None, idx=0):
		return None

	def set_selection(self,item):
		self.last_known_selection = item


class BricksTree(VBTree):
	""" Ordering bricks treeview. """
	def _bricks_treeorder_continue(self, itr, field=None, asc=True, moved = False):
		if field is None:
			field = _("Type")
		nxt = self.model.iter_next(itr)
		if (nxt):
			br_itr = self.model.get_value(itr, 0)
			br_nxt = self.model.get_value(nxt, 0)
			if field == _('Icon') or field == _('Type'):
				x = br_nxt.get_type()
				y = br_itr.get_type()
			elif field == _('Status'):
				x = br_nxt.proc
				y = br_itr.proc
			elif field == _('Name'):
				x = br_nxt.name
				y = br_itr.name
			elif field == _('Parameters'):
				x = br_nxt.get_parameters()
				y = br_itr.get_parameters()
			else:
				x = 0
				y = 0

			if asc:
				if x < y:
					self.model.swap(itr,nxt)
					moved = True
			else:
				if x > y:
					self.model.swap(itr,nxt)
					moved = True
			if x == y:
				if br_itr.name > br_nxt.name:
					self.model.swap(itr,nxt)
					moved = True

			return self._bricks_treeorder_continue(nxt, field, asc, moved)
		else:
			return moved

	def get_selection(self, pthinfo=None, idx=0):
		if pthinfo is not None:
			path, col, cellx, celly = pthinfo
			self.tree.grab_focus()
			self.tree.set_cursor(path, col, 0)
		else:
			path = self.tree.get_cursor()[0]
		if path is None:
			'''
			' Default to something that makes sense,
			' otherwise on_config_ok will be broken
			' when treeviews lose their selections.
			'''
			return self.last_known_selection

		iter = self.model.get_iter(path)
		self.last_known_selection = self.model.get_value(iter, idx)
		return self.last_known_selection

	def order(self, field=None, ascending=True):
		if field is None:
			field = _("Type")
		self.last_order = field
		self.order_last_direction = ascending
		itr = self.model.get_iter_first()
		if itr is None:
			return
		moved = self._bricks_treeorder_continue(itr, field, ascending)
		while moved:
			itr = self.model.get_iter_first()
			moved = self._bricks_treeorder_continue(itr, field, ascending)

	def cell_render(self, column, cell, mod, iter):
		brick = mod.get_value(iter, 0)
		assert brick is not None
		if column.get_title() == _('Icon'):
			if brick.homehost is not None and not brick.homehost.connected:
				icon = gtk.gdk.pixbuf_new_from_file_at_size(
					graphics.get_image("Disconnect.png"), 48, 48)
				cell.set_property('pixbuf', icon)
			elif brick.proc is not None:
				icon = gtk.gdk.pixbuf_new_from_file_at_size(
					graphics.get_brick_icon(brick), 48, 48)
				cell.set_property('pixbuf', icon)
			elif not brick.properly_connected():
				cell.set_property('stock-id', gtk.STOCK_DIALOG_ERROR)
				cell.set_property('stock-size', gtk.ICON_SIZE_LARGE_TOOLBAR)
			else:
				icon = gtk.gdk.pixbuf_new_from_file_at_size(
					graphics.get_brick_icon(brick), 48, 48)
				cell.set_property('pixbuf', icon)
		elif column.get_title() == _('Status'):
			cell.set_property('text', brick.get_state())
		elif column.get_title() == _('Type'):
			if brick.homehost:
				cell.set_property('text', "Remote " + brick.get_type() +" on " + brick.homehost.addr[0])
			else:
				cell.set_property('text', brick.get_type())
		elif column.get_title() == _('Name'):
			cell.set_property('text', brick.name)
		elif column.get_title() == _('Parameters'):
			cell.set_property('text', brick.get_parameters())
		else:
			raise NotImplementedError("cell_render not implemented for "
							"column %s" % column.get_title())


class EventsTree(VBTree):
	""" Ordering events treeview. """
	def _events_treeorder_continue(self, itr, field=None, asc=True, moved = False):
		if field is None:
			field = _("Type")
		nxt = self.model.iter_next(itr)
		if (nxt):
			br_itr = self.model.get_value(itr, 0)
			br_nxt = self.model.get_value(nxt, 0)
			if field == _('Icon') or field == _('Type'):
				x = br_nxt.get_type()
				y = br_itr.get_type()
			elif field == _('Status'):
				x = br_nxt.get_state()
				y = br_itr.get_state()
			elif field == _('Name'):
				x = br_nxt.name
				y = br_itr.name
			elif field == _('Parameters'):
				x = br_nxt.get_parameters()
				y = br_itr.get_parameters()
			else:
				x = 0
				y = 0

			if asc:
				if x < y:
					self.model.swap(itr,nxt)
					moved = True
			else:
				if x > y:
					self.model.swap(itr,nxt)
					moved = True
			if x == y:
				if br_itr.name > br_nxt.name:
					self.model.swap(itr,nxt)
					moved = True

			return self._events_treeorder_continue(nxt, field, asc, moved)
		else:
			return moved

	def get_selection(self, pthinfo=None, idx=0):
		if pthinfo is not None:
			path, col, cellx, celly = pthinfo
			self.tree.grab_focus()
			self.tree.set_cursor(path, col, 0)
		else:
			path = self.tree.get_cursor()[0]
		if path is None:
			'''
			' Default to something that makes sense,
			' otherwise on_config_ok will be broken
			' when treeviews lose their selections.
			'''
			return self.last_known_selection

		iter = self.model.get_iter(path)
		self.last_known_selection = self.model.get_value(iter, idx)
		return self.last_known_selection

	def order(self, field=None, ascending=True):
		if field is None:
			field = _("Type")
		self.last_order = field
		self.order_last_direction = ascending
		itr = self.model.get_iter_first()
		if itr is None:
			return
		moved = self._events_treeorder_continue(itr, field, ascending)
		while moved:
			itr = self.model.get_iter_first()
			moved = self._events_treeorder_continue(itr, field, ascending)

	def cell_render(self, column, cell, mod, iter):
		event = mod.get_value(iter, 0)
		assert event is not None
		if column.get_title() == _('Icon'):
			icon = gtk.gdk.pixbuf_new_from_file_at_size(
				graphics.get_brick_icon(event), 48, 48)
			cell.set_property('pixbuf', icon)
		elif column.get_title() == _('Status'):
			cell.set_property('text', event.get_state())
		elif column.get_title() == _('Type'):
			cell.set_property('text', event.get_type())
		elif column.get_title() == _('Name'):
			cell.set_property('text', event.name)
		elif column.get_title() == _('Parameters'):
			cell.set_property('text', event.get_parameters())
		else:
			raise NotImplementedError("cell_render")


# vim: set noet :

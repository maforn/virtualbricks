#!/usr/bin/python
# coding: utf-8

"""
Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) 2011 Virtualbricks team

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import functools
import gtk
import new

from virtualbricks.logger import ChildLogger

class Logger(ChildLogger):
	def __init__(self, glade):
		ChildLogger.__init__(self)
		self.glade = glade

		self.messages_buffer = gtk.TextBuffer()

		tags = {
			'debug': {'foreground': '#a29898'},
			'info': { },
			'warning': {'foreground': '#ff9500'},
			'error': {'foreground': '#b8032e'},
			'critical': {'foreground': '#b8032e', 'background': '#000'},
			'exception': {'foreground': '#000', 'background': '#b8032e'},
		}

		for level, properties in tags.iteritems():
			tag = self.messages_buffer.create_tag(level)
			for property_name, value in properties.iteritems():
				tag.set_property(property_name, value)
			function = functools.partial(Logger._log, level=level)
			method = new.instancemethod(function, None, Logger)
			setattr(Logger, level, method)

	def _log(self, text, *args, **kwargs):
		"""log text at level specified by kwargs['level']"""
		level = kwargs.pop('level')
		if args:
			text = unicode(text) % args
		#else:
		#	text = "[unknown message]"
		pos = self.messages_buffer.get_end_iter()
		self.messages_buffer.insert_with_tags_by_name(pos, "%s\n" % text, level)
		txtbox = self.glade.get_widget('messages_textview')
		txtbox.scroll_mark_onscreen(txtbox.get_buffer().get_insert())
		# OR:
		#self.glade.get_widget('messages_textview').scroll_to_mark(self.messages_buffer.get_insert(), 0)


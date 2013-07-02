import os
import os.path
import struct
import StringIO

from virtualbricks import tools
from virtualbricks.tests import unittest


class MockLock(object):

    def __init__(self):
        self.c = 0

    def __enter__(self):
        self.c += 1

    def __exit__(self, exc_type, exc_value, traceback):
        pass


HELLO = "/hello/backingfile"
COW_HEADER = "OOOM\x00\x00\x00\x02" + HELLO + "\x00" * 1006
QCOW_HEADER = "QFI\xfb\x00\x00\x00\x01" + struct.pack(">Q", 20) + \
        struct.pack(">I", len(HELLO)) + HELLO
QCOW_HEADER0 = "QFI\xfb\x00\x00\x00\x01" + "\x00" * 12
QCOW_HEADER2 = "QFI\xfb\x00\x00\x00\x02" + struct.pack(">Q", 20) + \
        struct.pack(">I", len(HELLO)) + HELLO
UNKNOWN_HEADER = "MOOO\x00\x00\x00\x02"


class TestTools(unittest.TestCase):

    def test_sincronize_with(self):
        lock = MockLock()
        foo_s = tools.synchronize_with(lock)(lambda: None)
        foo_s()
        self.assertEqual(lock.c, 1)
        foo_s()
        self.assertEqual(lock.c, 2)

    def test_tempfile_context(self):
        with tools.Tempfile() as (fd, filename):
            os.close(fd)
            self.assertTrue(os.path.isfile(filename))
        try:
            with tools.Tempfile() as (fd, filename):
                os.close(fd)
                raise RuntimeError
        except RuntimeError:
            self.assertFalse(os.path.isfile(filename))

    def test_backing_file_from_cow(self):
        sio = StringIO.StringIO(COW_HEADER[8:])
        backing_file = tools.get_backing_file_from_cow(sio)
        self.assertEqual(backing_file, HELLO)

    def test_backing_file_from_qcow0(self):
        sio = StringIO.StringIO(QCOW_HEADER0[8:])
        backing_file = tools.get_backing_file_from_qcow(sio)
        self.assertEqual(backing_file, "")

    def test_backing_file_from_qcow(self):
        sio = StringIO.StringIO(QCOW_HEADER)
        sio.seek(8)
        backing_file = tools.get_backing_file_from_qcow(sio)
        self.assertEqual(backing_file, HELLO)

    def test_backing_file(self):
        for header in COW_HEADER, QCOW_HEADER, QCOW_HEADER2:
            sio = StringIO.StringIO(header)
            backing_file = tools.get_backing_file(sio)
            self.assertEqual(backing_file, "/hello/backingfile")

        sio = StringIO.StringIO(UNKNOWN_HEADER)
        self.assertRaises(tools.UnknowTypeError, tools.get_backing_file, sio)

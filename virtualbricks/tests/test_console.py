import StringIO
import textwrap

from virtualbricks import console, errors
from virtualbricks.tests import unittest, stubs


class TestProtocol(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.stdout = StringIO.StringIO()

    def parse(self, cmd):
        console.parse(self.factory, cmd, self.stdout)

    def discard_output(self):
        self.stdout.seek(0)
        self.stdout.truncate()

    def get_value(self):
        ret = self.stdout.getvalue()
        self.discard_output()
        return ret[len(console.VBProtocol.intro) +
                   len(console.VBProtocol.prompt) + 1:
                   -len(console.VBProtocol.prompt)]

    def test_new_brick(self):
        self.parse("new stub test")
        self.discard_output()
        self.assertEquals(len(self.factory.bricks), 1)
        self.assertEquals(self.factory.bricks[0].name, "test")
        self.assertEquals(self.factory.bricks[0].get_type(), "Stub")
        self.parse("new stub t+")
        self.assertEqual(self.get_value(),
                         "Name must contains only letters, "
                         "numbers, underscores, hyphens and points, t+\n")
        cmd = "new stub"
        self.parse(cmd)
        self.assertEqual(self.get_value(), "invalid command %s\n" % cmd)
        cmd = "new"
        self.parse(cmd)
        self.assertEqual(self.get_value(), "invalid command %s\n" % cmd)
        self.flushLoggedErrors(TypeError)

    def test_new_event(self):
        self.parse("new event test_event")
        self.assertEquals(len(self.factory.events), 1)
        self.assertEquals(self.factory.events[0].name, "test_event")
        self.assertEquals(self.factory.events[0].get_type(), "Event")

    def test_quit_command(self):
        result = []
        self.factory.quit = lambda: result.append(True)
        self.parse("quit")
        self.assertEqual(result, [True])

    def test_help_command(self):
        self.discard_output()
        self.parse("help")
        self.assertEqual(self.get_value(),
                         textwrap.dedent(console.VBProtocol.__doc__) + "\n")

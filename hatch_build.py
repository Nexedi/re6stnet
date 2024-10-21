import tempfile
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.metadata.plugin.interface import MetadataHookInterface

version = {"__file__": "re6st/version.py"}
with open(version["__file__"]) as f:
    code = compile(f.read(), version["__file__"], 'exec')
    exec(code, version)


class CustomMetadataHook(MetadataHookInterface):

    def update(self, metadata):
        metadata['version'] = egg_version = "0.%(revision)s" % version
        metadata['readme'] = {
            'content-type': 'text/x-rst',
            'text': ".. contents::\n\n" + open('README.rst').read()
                    + "\n" + open('CHANGES.rst').read() + """

Git Revision: %s == %s
""" % (egg_version, version["short"]),
        }


class CustomBuildHook(BuildHookInterface):

    def initialize(self, _, build_data):
        f = self.__version = tempfile.NamedTemporaryFile('w')
        for x in sorted(version.items()):
            if not x[0].startswith("_"):
                f.write("%s = %r\n" % x)
        f.flush()
        build_data["force_include"][f.name] = version["__file__"]

    def finalize(self, *_):
        self.__version.close()

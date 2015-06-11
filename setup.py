"""Resilient, Scalable, IPv6 Network
"""

from setuptools import setup, find_packages
from setuptools.command import sdist as _sdist, build_py as _build_py
from distutils import log

version = {"__file__": "re6st/version.py"}
execfile(version["__file__"], version)

def copy_file(self, infile, outfile, *args, **kw):
    if infile == version["__file__"]:
        if not self.dry_run:
            log.info("generating %s -> %s", infile, outfile)
            with open(outfile, "wb") as f:
                for x in sorted(version.iteritems()):
                    if not x[0].startswith("_"):
                        f.write("%s = %r\n" % x)
        return outfile, 1
    cls, = self.__class__.__bases__
    return cls.copy_file(self, infile, outfile, *args, **kw)

class build_py(_build_py.build_py):
    copy_file = copy_file

class sdist(_sdist.sdist):
    copy_file = copy_file

classifiers = """\
Environment :: Console
License :: OSI Approved :: GNU General Public License (GPL)
Natural Language :: English
Operating System :: POSIX :: Linux
Programming Language :: Python :: 2.6
Programming Language :: Python :: 2.7
Topic :: Internet
Topic :: System :: Networking
"""

egg_version = "0.%(revision)s" % version

git_rev = """

Git Revision: %s == %s
""" % (egg_version, version["short"])

setup(
    name = 're6stnet',
    version = egg_version,
    description = __doc__.strip(),
    author = 'Nexedi',
    author_email = 're6stnet@erp5.org',
    url = 'http://re6st.net',
    license = 'GPL 2+',
    platforms = ["any"],
    classifiers=classifiers.splitlines(),
    long_description = ".. contents::\n\n" + open('README').read()
                     + "\n" + open('CHANGES').read() + git_rev,
    packages = find_packages(),
    entry_points = {
        'console_scripts': [
            're6st-conf=re6st.cli.conf:main',
            're6stnet=re6st.cli.node:main',
            're6st-registry=re6st.cli.registry:main',
        ],
    },
    package_data = {
        're6st': [
            'ovpn-server',
            'ovpn-client',
        ],
    },
    # BBB: use MANIFEST.in only so that egg_info works with very old setuptools
    include_package_data = True,
    install_requires = ['pyOpenSSL >= 0.13', 'miniupnpc'],
    #dependency_links = [
    #    "http://miniupnp.free.fr/files/download.php?file=miniupnpc-1.7.20120714.tar.gz#egg=miniupnpc-1.7",
    #    ],
    zip_safe = False,
    cmdclass=dict(build_py=build_py, sdist=sdist),
)

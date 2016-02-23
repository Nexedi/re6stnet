"""Resilient, Scalable, IPv6 Network
"""
import os, stat
from distutils.command.build_scripts import first_line_re
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
    elif isinstance(self, build_py) and \
         os.stat(infile).st_mode & stat.S_IEXEC:
        # Adjust interpreter of OpenVPN hooks.
        with open(infile) as src:
            first_line = src.readline()
            m = first_line_re.match(first_line)
            if m and not self.dry_run:
                log.info("copying and adjusting %s -> %s", infile, outfile)
                executable = self.distribution.command_obj['build'].executable
                patched = "#!%s%s\n" % (executable, m.group(1) or '')
                patched += src.read()
                dst = os.open(outfile, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
                try:
                    os.write(dst, patched)
                finally:
                    os.close(dst)
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
    long_description = ".. contents::\n\n" + open('README.rst').read()
                     + "\n" + open('CHANGES.rst').read() + git_rev,
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

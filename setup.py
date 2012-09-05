"""Resilient, Scalable, IPv6 Network
"""

from setuptools import setup, find_packages

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

setup(
    name = 're6stnet',
    version = '0.1',
    description = __doc__.strip(),
    author = 'Nexedi',
    author_email = 're6stnet@erp5.org',
    url = 'http://re6st.net',
    license = 'GPL 2+',
    platforms = ["any"],
    classifiers=classifiers.splitlines(),
    long_description = ".. contents::\n\n" + open('README').read()
                     + "\n" + open('CHANGES').read(),
    packages = find_packages(),
    scripts = [
            're6stnet',
            're6st-conf',
            're6st-registry',
        ],
    package_data = {
        're6st': [
            'ovpn-server',
            'ovpn-client',
        ],
    },
    install_requires = ['pyOpenSSL', 'miniupnpc'],
    #dependency_links = [
    #    "http://miniupnp.free.fr/files/download.php?file=miniupnpc-1.7.20120714.tar.gz#egg=miniupnpc-1.7",
    #    ],
    zip_safe = False,
)

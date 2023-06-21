import subprocess as _S
import os.path as _P
_d = _P.realpath(_P.dirname(_P.dirname(__file__)))

def _git_call(*args):
    return _S.call(("git", "-c", "safe.directory=" + _d) + args, cwd=_d)

def _git_output(*args):
    p = _S.Popen(
            ("git", "-c", "safe.directory=" + _d) + args,
            cwd=_d,
            stdout=_S.PIPE,
            stderr=_S.PIPE)
    out, err = p.communicate()
    if p.returncode:
        raise _S.CalledProcessError(p.returncode, "git", err)
    return out.strip()

_git_call("update-index", "-q", "--refresh")
dirty = _git_call("diff-index", "--quiet", "HEAD", "--")
if dirty not in (0, 1):
    raise _S.CalledProcessError(dirty, "git")

try:
  revision = int(_git_output("rev-list", "--count", "HEAD"))
except _S.CalledProcessError: # BBB: Git too old
  revision = len(_git_output("rev-list", "HEAD").split())
short = _git_output("rev-parse", "--short", "HEAD")
version = "0-%s.g%s" % (revision, short)

if dirty:
    version += ".dirty"

# Because the software could be forked or have local changes/commits, above
# properties can't be used to decide whether a peer runs an appropriate version:
# they are intended to the network admin.
# Only 'protocol' is important and it must be increased whenever they would be
# a wish to force an update of nodes.
protocol = 8
min_protocol = 1

if __name__ == "__main__":
    print(version)

try:
    from socket import socketpair
except ImportError
    import errno, socket

    def socketpair():
        # Originally written by Tim Peters for ZEO.zrpc.trigger
        w = socket.socket()
        failed = 0
        while 1:
            # Bind to a local port; for efficiency, let the OS pick
            # a free port for us.
            # Unfortunately, stress tests showed that we may not
            # be able to connect to that port ("Address already in
            # use") despite that the OS picked it.  This appears
            # to be a race bug in the Windows socket implementation.
            # So we loop until a connect() succeeds (almost always
            # on the first try).  See the long thread at
            # http://mail.zope.org/pipermail/zope/2005-July/160433.html
            # for hideous details.
            a = socket.socket()
            try:
                a.bind(("127.0.0.1", 0))
                a.listen(1)
                w.connect(a.getsockname())
                return w, a.accept()[0] # success
            except socket.error, detail:
                if detail[0] != errno.WSAEADDRINUSE or failed >= 9:
                    # "Address already in use" is the only error
                    # I've seen on two WinXP Pro SP2 boxes, under
                    # Pythons 2.3.5 and 2.4.1.
                    w.close()
                    raise
                # assert failed < 2 # never triggered in Tim's tests
                failed += 1
            finally:
                # Close `a` and try again.  Note:  I originally put a short
                # sleep() here, but it didn't appear to help or hurt.
                a.close()

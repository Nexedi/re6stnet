#include <windows.h>

extern sscanf (const char *, const char *, ...);

HANDLE open_pipe (const char *pname)
{
  HANDLE proc, pipe_hdl, nio_hdl = NULL;
  int pid, rwflags = 1; /* O_WRONLY */

  sscanf (pname, "/proc/%d/fd/pipe:[%d]", &pid, (int *) &pipe_hdl);

  if (!(proc = OpenProcess (PROCESS_DUP_HANDLE, FALSE, pid))) {
    return NULL;
  }

  if (!DuplicateHandle (proc, pipe_hdl, GetCurrentProcess (), &nio_hdl,
                        0, FALSE, DUPLICATE_SAME_ACCESS)) {
    return NULL;
  }
  CloseHandle (proc);
  return nio_hdl;
}


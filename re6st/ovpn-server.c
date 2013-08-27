#include <stdio.h>
/*
if os.environ['script_type'] == 'client-connect':
    # Send client its external ip address
    with open(sys.argv[2], 'w') as f:
        f.write('push "setenv-safe external_ip %s"\n'
                % os.environ['trusted_ip'])

# Write into pipe connect/disconnect events
arg1 = sys.argv[1]
if arg1 != 'None':
    os.write(int(arg1), '%(script_type)s %(common_name)s %(trusted_ip)s\n'
                        % os.environ)
*/
int main(int argc, char *argv[])
{
  char *p;
  int pd;
  char buf[512];
  int n;
  char *s, *s1, *s2;
  int fd;

  s = (char*)getenv("script_type");
  if (s == NULL) {
    fprintf(stderr, "no script_type\n");
    return 1;
  }

  s2 = (char*)getenv("trusted_ip");
  if (s2 == NULL) {
    fprintf(stderr, "no trusted_ip\n");
    return 1;
  }
 
  if (strcmp(s, "client-connect") == 0) {
    if (argc < 3) {
      fprintf(stderr, "missing filename\n");
      return 1;
    }    
    n = snprintf(buf, 512, "push \"setenv-safe external_ip %s\"\n", s2);
    if (n >= 512) {
      fprintf(stderr, "buffer overflow\n");
      return 1;
    }

    /* O_WRONLY == 1 */
    fd = open(argv[2], 1);
    if (fd == -1) {
      fprintf(stderr, "open %s failed\n", argv[2]);
      return 1;    
    }

    if (write(fd, buf, n) == -1) {
      fprintf(stderr, "write %s failed\n", argv[2]);
      close(fd);
      return 1;
    }
    close(fd);
  }

  if (argc < 2) {
    fprintf(stderr, "missing pipe\n");
    return 1;
  }

  if (strcmp(argv[1], "None") == 0)
    return 0;

  pd = strtol(argv[1], &p, 10);
  if (! (*p == 0)) {
    fprintf(stderr, "invalid pipe %s\n", argv[1]);
    return 1;
  }

  /* %(script_type)s %(common_name)s %(OPENVPN_external_ip)s */
  s1 = (char*)getenv("common_name");
  if (s1 == NULL) {
    fprintf(stderr, "missing common_name\n");
    return 1;
  }

  n = snprintf(buf, 512, "%s %s %s\n", s, s1, s2);
  if (n >= 512) {
    fprintf(stderr, "buffer overflow\n");
    return 1;
  }

  if (write(pd, buf, n) == -1) {
    fprintf(stderr, "write pipe failed\n");
    return 1;
  }

  return 0;
}

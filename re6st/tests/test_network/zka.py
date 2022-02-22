import os
import sys

with open(os.devnull, "wb") as null:
    tmp = sys.stderr
    sys.stderr = null
    import re6st.tests.tools as tools
    sys.stderr = tmp

# tools.create_ca_file("10","12")
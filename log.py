import time

def log(message, verbose_level):
    if verbose >= verbose_level:
        print time.strftime("%d-%m-%Y %H:%M:%S : " + message)


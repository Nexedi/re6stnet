import matplotlib.pyplot as plt

max_peers = 30
nFiles = 2
nRounds = 3000
file_names = ['out_%s.csv' % i for i in range(nFiles)]

distance = [0] * nRounds

arity = [[0] * 31 for i in range(nRounds)]

for file_name in file_names:
    # open the file
    f = open(file_name, 'r')
    lines = f.read().split('\n')

    for line in lines:
        vals = line.split(',')
        if len(vals) < 2:
            continue

        i = int(vals[0])
        if i >= nRounds:
            continue

        distance[i] += float(vals[1])
        for j in range(0, 31):
            arity[i][j] += float(vals[j + 2])

for i in range(0, nRounds):
    distance[i] = distance[i] / len(file_names)
    for j in range(0, 31):
        arity[i][j] = arity[i][j] / len(file_names)

plt.plot(range(31), arity[1], range(31), arity[nRounds - 1])
plt.legend(('Random network', 'After %s iterations' % nRounds))
plt.xlabel('Arity')
plt.ylabel('Ratio of node')
plt.axis([10, 30, 0, 0.4])
#plt.xscale('log')
plt.show()


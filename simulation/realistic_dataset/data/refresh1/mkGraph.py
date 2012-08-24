import matplotlib.pyplot as plt

max_peers = 30
nFiles = 4
nRounds = 900
file_names = ['out_%s.csv' % i for i in range(nFiles)]

distance = [0] * nRounds
arityLat = [[0] * (max_peers - 9) for i in range(10)]

arity = [[0] * (max_peers + 1) for i in range(nRounds)]

for file_name in file_names:
    # open the file
    f = open(file_name, 'r')
    lines = f.read().split('\n')

    for line in lines:
        vals = line.split(',')
        i = int(vals[0])

        distance[i] += float(vals[1])
        for j in range(10, 31):
            arity[i][j] += float(vals[j - 6])

        for j in range(0, 10):
            for k in range(0, max_peers - 9):
                arityLat[j][k] += int(vals[48 + 22 * j + k])

for i in range(0, nRounds):
    distance[i] = distance[i] / len(file_names)
    for j in range(0, 31):
        arity[i][j] = arity[i][j] / len(file_names)

for i in range(0, 10):
    s = sum(arityLat[i])
    for j in range(0, max_peers - 9):
        arityLat[i][j] = float(arityLat[i][j]) / float(s)

#plt.plot(range(31), arity[1], range(31), arity[nRounds - 1])
#plt.legend(('Random network', 'After %s iterations' % nRounds))
#plt.xlabel('Arity')
#plt.axis([10, 30, 0, 0.3])

latRange = range(10, 31)
plt.plot(latRange, arityLat[0], latRange, arityLat[9])
plt.legend(('average latency < 50ms', 'average latency > 90ms'), loc=2)
plt.xlabel('Arity')

#plt.plot(range(0, nRounds), distance)

#plt.yscale('log')
plt.show()


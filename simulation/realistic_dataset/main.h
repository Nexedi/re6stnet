#include <iostream>
#include <vector>
#include <random>
#include <queue>
#include <stack>
#include <unordered_set>
#include <future>
#include <sstream>
#include <unistd.h>

using namespace std;


class Latency
{
public:
	Latency(const char* filePath, int size);
    void Rewrite(int n);
    ~Latency();
    int** values;

private:
	int size;
};

class Graph
{
public:
    Graph(int size, int k, int maxPeers, mt19937& generator, const Latency& latency);
    Graph(const Graph& g);
    ~Graph() { delete[] adjacency; delete[] generated; };
    void UpdateLowRoutes(double& avgDistance, double unreachable, double* arityDistrib);
    double GetUnAvalaibility();
    void KillMachines(float proportion);

private:
    void SaturateNode(int node);
	bool AddEdge(int from);
    void RemoveEdge(int from, int to);
    void GetRoutesFrom(int from, int* nRoutes, int* prevs, int* distances);
    int CountUnreachableFrom(int node);

    mt19937& generator;
    uniform_int_distribution<int> distrib;
    int maxPeers;
    int k;
    int size;

    unordered_set<int>* adjacency;
    unordered_set<int>* generated;
    const Latency& latency;
};

struct routesResult
{
    double avgDistance;
    int arity;
    int unreachable;
    int toDelete;
};
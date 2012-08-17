#include <iostream>
#include <vector>
#include <random>
#include <queue>
#include <stack>
#include <unordered_set>
#include <future>
#include <sstream>
#include <unistd.h>
#include <limits>

using namespace std;

struct routesResult
{
    double avgDistance;
    int arity;
    int unreachable;
    int routesToDelete;
    stack<int> toDelete;
};

class Latency
{
public:
	Latency(const char* filePath, int size);
    void Rewrite(int n);
    ~Latency();
    double GetAverageDistance();
    double GetAveragePing();
    int** values;
    double* avgLatencyToOthers;

private:
	int size;
};

class Graph
{
public:
    Graph(int size, int k, int maxPeers, mt19937& generator, Latency* latency);
    Graph(Graph& g);
    ~Graph() { delete[] adjacency; delete[] generated;};
    int UpdateLowRoutes(double& avgDistance, double& unreachable, double& nRoutesKilled, double* arityDistrib, double* bcArity, int nRefresh, int round);
    double GetUnAvalaibility();
    void Reboot(double proba, int round);
    void KillMachines(float proportion);
    pair<double, double> UpdateLowRoutesArity(int arityToUpdate);
    void GetArity(int* arity);
    void GetRoutesFrom(int from, int* nRoutes, int* prevs, int* distances);
    double GetAvgDistanceHop();
    void GetArityLat(int arity[][10]);
    
private:
    void SaturateNode(int node);
	bool AddEdge(int from);
    void RemoveEdge(int from, int to);
    int CountUnreachableFrom(int node);
    routesResult GetRouteResult(int node, int nRefresh, double* bc);

    mt19937 generator;
    uniform_int_distribution<int> distrib;
    int maxPeers;
    int k;
    int size;

    unordered_set<int>* adjacency;
    unordered_set<int>* generated;
    Latency* latency;
};

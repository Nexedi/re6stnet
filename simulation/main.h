#include <iostream>
#include <vector>
#include <random>
#include <queue>
#include <set>

using namespace std;

class Graph
{
public:
    Graph(int size, int k, int maxPeers, mt19937 rng);
    ~Graph() { delete[] adjacency; };

    void GetDistancesFrom(int node, int* distance);
    void KillMachines(float proportion);
   
    vector<int>* adjacency;
    int size;
private:
    uniform_int_distribution<int> distrib;
};

class Results
{
public:
    Results(int maxArity, int maxDistance);
    ~Results();

    void UpdateArity(const Graph& graph);
    void UpdateDistance(int* distance, int nSamples);
    void Finalise();

    double* arityDistrib;
    double* distanceDistrib;
    double disconnectionProba;
    double arityTooBig;
    double distanceTooBig;
    int64_t disconnected;
    int64_t nAritySample;
    int64_t nDistanceSample;
    int maxArity;
    int maxDistance;

private:
    void AddAritySample(int arity);
    void AddDistanceSample(int distance);
};

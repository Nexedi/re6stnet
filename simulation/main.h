#include <iostream>
#include <vector>
#include <random>
#include <queue>
#include <set>
#include <unordered_set>

using namespace std;

template<class T>
struct nullable
{
    T v;
    bool null;

    nullable() : null(false) { };
    nullable(T t) : v(t), null(false) { };
};

class MinCutGraph
{
public:
    vector<nullable<pair<int, int>>> edges;
    vector<nullable<unordered_set<int>>> nodes;
    MinCutGraph(vector<int>* adjacency, int n);
    void Merge(int nMerge, mt19937& rng);
private:
    void Check();
    void RenumEdges();
    void RenumNodes();
};


class Graph
{
public:
    Graph(int size, int k, int maxPeers, mt19937& rng);
    ~Graph() { delete[] adjacency; };

    void GetDistancesFrom(int node, int* distance);
    int GetMinCut();
    int CountUnreachableFrom(int node);

    void KillMachines(float proportion);
    //void SplitAS(float proportionAS1, float proportionAS2);

    vector<int>* adjacency;
    int size;
private:
    int GetMinCut(MinCutGraph& graph);

    uniform_int_distribution<int> distrib;
    mt19937& generator;
};

class Results
{
public:
    Results(int maxArity, int maxDistance);
    ~Results();

    void UpdateArity(const Graph& graph);
    void AddAccessibilitySample(double accessibility);
    void UpdateDistance(int* distance, int nSamples);
    void Finalise();

    double* arityDistrib;
    double* distanceDistrib;
    double avgDistance;
    double avgAccessibility;
    int maxDistanceReached;
    int minKConnexity;

    double disconnectionProba;
    double arityTooBig;
    double distanceTooBig;
    int64_t disconnected;

    int maxArity;
    int maxDistance;

private:
    void AddAritySample(int arity);
    void AddDistanceSample(int distance);

    int64_t nAritySample;
    int64_t nDistanceSample;
    int64_t nAccessibilitySample;
};

#include <iostream>
#include <vector>
#include <random>
#include <queue>
#include <set>

#define max(a,b) a>b?a:b
#define min(a,b) a<b?a:b
#define clamp(a,b,c) max(a,min(b, c))
#define array(name, size) name[size]; for(int i=0; i<size; i++) name[i]=0;

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


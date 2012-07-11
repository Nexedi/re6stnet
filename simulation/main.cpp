// To compile with -std=c++0x
#include "main.h"
#include <fstream>

int n = 1000; // the number of peer
int k = 10; // each peer try to make k connections with the others
const char* outName = "out.csv";


Results Simulate(mt19937 rng,  int n, int k, int maxPeer, int maxDistanceFrom, int runs)
{
    Results results(maxPeer, 20);

    for(int r=0; r<runs; r++)
    {
        cout << "\r                                          \rn = " << n << ", k = " << k << ", run = " << r;
        cout.flush();

        Graph graph(n, k, maxPeer, rng);
        results.UpdateArity(graph);

        // Compute the shortest path
        for(int i=0; i<min(graph.size, maxDistanceFrom); i++)
        {
            int distance[graph.size];
            graph.GetDistancesFrom(i, distance);
            results.UpdateDistance(distance, graph.size);
        }
    }
    cout << "\r                                              \r";

    results.Finalise();
    return results;
}

int main(int argc, char** argv)
{
    mt19937 rng(time(NULL));

    fstream output(outName, fstream::out);
    output << "n,k,maxPeer,avgDistance,disconnected,maxDistance,maxArityDistrib" << endl;

    for(int n=200; n<=20000; n*=2)
        for(int k=5; k<=50; k+=5)
        {
            Results results = Simulate(rng, n, k, 3*k, 10000, 50);
            output << n << "," << k << "," << 3*k << "," << results.avgDistance << "," 
                << results.disconnected << ","  << results.maxDistance << ","
                << results.arityDistrib[3*k] << endl;
        }

    output.close();
    return 0;
}



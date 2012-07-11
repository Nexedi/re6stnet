// To compile with -std=c++0x
#include "main.h"

int n = 1000; // the number of peer
int k = 10; // each peer try to make k connections with the others
int maxPeer = 25; // no more that 25 connections per peer
int runs = 10;  // use this to run the simulation multiple times to get more accurate values

int main()
{
    mt19937 rng(time(NULL));
    Results results(maxPeer, 20);

    for(int r=0; r<runs; r++)
    {
        cout << "\r       \rRun " << r;
        cout.flush();

        Graph graph(n, k, maxPeer, rng);
        results.UpdateArity(graph);

        // Compute the shortest path
        for(int i=0; i<graph.size; i++)
        {
            int distance[graph.size];
            graph.GetDistancesFrom(i, distance);
            results.UpdateDistance(distance, graph.size);
        }
    }
    cout << "\r            \r";

    results.Finalise();

    // Display the parameters we have mesured
    cout << "Arity :" << endl;
    for(int i=0; i<=results.maxArity; i++)
        if(results.arityDistrib[i] != 0)
            cout << i << " : " << results.arityDistrib[i] << endl;
    
    cout << "Distance :" << endl;
    double nLinks = n*(n-1)*runs;
    for(int i=0; i<= results.maxDistance; i++)
        if(results.distanceDistrib[i] != 0)
            cout << i << " : " << results.distanceDistrib[i] << endl;
    
    cout << "Probability that a node is not reachable : " 
         << results.disconnectionProba
         << " (" << results.disconnected << " total)" << endl;

    cout << endl;
    return 0;
}



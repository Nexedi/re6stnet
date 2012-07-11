// To compile : g++ -std=c++0x results.cpp graph.cpp main.cpp -lpthread
#include "main.h"
#include <fstream>
#include <future>
#include <sstream>

const char* outName = "out.csv";


Results Simulate(mt19937 rng,  int n, int k, int maxPeer, int maxDistanceFrom, int runs)
{
    Results results(maxPeer, 20);

    for(int r=0; r<runs; r++)
    {
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

    results.Finalise();
    return results;
}

int main(int argc, char** argv)
{
    mt19937 rng(time(NULL));

    fstream output(outName, fstream::out);
    output << "n,k,maxPeer,avgDistance,disconnected,maxDistance,maxArityDistrib" << endl;


    vector<future<string>> outputStrings;
    for(int n=200; n<=20000; n*=2)
        for(int k=5; k<=50; k+=5)
        {
            outputStrings.push_back(async(launch::async, [rng, n, k]() 
                {
                    Results results = Simulate(rng, n, k, 3*k, 10000, 50);
                    ostringstream out;
                    out << n << "," << k << "," << 3*k << "," << results.avgDistance << ","
                        << results.disconnected << ","  << results.maxDistance << ","
                        << results.arityDistrib[3*k];

                    return out.str();
                }));
        }

    cout << "Launching finished" << endl;

    int nTask = outputStrings.size();
    for(int i=0; i<nTask; i++)
    {
        output << outputStrings[i].get() << endl;
        cout << "\r" << i << "/" << nTask;
        cout.flush();
    }

    cout << endl;
    output.close();
    return 0;
}



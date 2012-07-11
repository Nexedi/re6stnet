// To compile : g++ -std=c++0x results.cpp graph.cpp main.cpp -lpthread
#include "main.h"
#include <future>
#include <sstream>

const char* outName = "out.csv";

Results Simulate(mt19937 rng,  int n, int k, int maxPeer, int maxDistanceFrom, float alivePercent, int runs)
{
    Results results(maxPeer, 20);

    for(int r=0; r<runs; r++)
    {
        Graph graph(n, k, maxPeer, rng);
        graph.KillMachines(alivePercent);
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

    FILE* output = fopen(outName, "wt");
    int fno = fileno(output);
    fprintf(output, "n,k,maxPeer,avgDistance,disconnected,disconnectionProba,maxDistance,maxArityDistrib\n");

    vector<future<string>> outputStrings;
    for(int n=200; n<=20000; n*=2)
        for(int k=10; k<=10; k+=5)
            for(float a=0.05; a<1; a+=0.05)
        {
            outputStrings.push_back(async(launch::async, [rng, n, k, a]() 
                {
                    Results results = Simulate(rng, n, k, 3*k, 10000, a, 100);
                    ostringstream out;
                    out << n << "," << k << "," << 3*k << "," << results.avgDistance << ","
                        << results.disconnected << "," << results.disconnectionProba << ","
                        << results.maxDistanceReached << "," << results.arityDistrib[3*k]
                        << endl;
                    return out.str();
                }));
        }

    cout << "Launching finished" << endl;

    int nTask = outputStrings.size();
    for(int i=0; i<nTask; i++)
    {
        fprintf(output, outputStrings[i].get().c_str());
        fflush(output);
        fsync(fno);
        cout << "\r" << i+1 << "/" << nTask;
        cout.flush();
    }


    cout << endl;
    fclose(output);
    return 0;
}



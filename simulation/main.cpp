// To compile : g++ -std=c++0x results.cpp graph.cpp main.cpp -lpthread
#include "main.h"
#include <future>
#include <sstream>

const char* outName = "out.csv";

Results Simulate(int seed,  int n, int k, int maxPeer, int maxDistanceFrom, float alivePercent, int runs)
{
    Results results(maxPeer, 20);
    mt19937 rng(seed);

    for(int r=0; r<runs; r++)
    {
        Graph graph(n, k, maxPeer, rng);
        graph.KillMachines(alivePercent);
        int minCut = graph.GetMinCut();
        if(results.minKConnexity == -1 || results.minKConnexity > minCut)
        results.minKConnexity = minCut;
        results.UpdateArity(graph);

        // Compute the shortest path
        /*for(int i=0; i<min(graph.size, maxDistanceFrom); i++)
        {
            int distance[graph.size];
            graph.GetDistancesFrom(i, distance);
            results.UpdateDistance(distance, graph.size);
        }*/
    }

    results.Finalise();
    return results;
}

int main(int argc, char** argv)
{
    mt19937 rng(time(NULL));

    FILE* output = fopen(outName, "wt");
    int fno = fileno(output);
    fprintf(output, "n,k,a,maxPeer,avgDistance,disconnected,disconnectionProba,maxDistance,maxArityDistrib,minCut\n");

    vector<future<string>> outputStrings;
    for(int n=2000; n<=2000; n*=2)
        for(int k=10; k<=10; k+=5)
            for(float a=1; a<=1; a+=0.05)
            {
                int seed = rng();
                outputStrings.push_back(async(launch::async, [seed, n, k, a]() 
                    {
                        Results results = Simulate(seed, n, k, 3*k, 10000, a, 1);
                        ostringstream out;
                        out << n << "," << k << "," << a << "," << 3*k << "," << results.avgDistance << ","
                            << results.disconnected << "," << results.disconnectionProba << ","
                            << results.maxDistanceReached << "," << results.arityDistrib[3*k] << "," << results.minKConnexity
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



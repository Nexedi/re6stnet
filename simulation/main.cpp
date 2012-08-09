// To compile : g++ -std=c++0x results.cpp graph.cpp main.cpp -lpthread 
#include "main.h"
#include <future>
#include <sstream>
#include <unistd.h>

const char* outName = "out.csv";

Results Simulate(int seed,  int n, int k, int maxPeer, int maxDistanceFrom, float alivePercent, int runs)
{
    Results results(maxPeer, 20);
    mt19937 rng(seed);

    for(int r=0; r<runs; r++)
    {
        Graph graph(n, k, maxPeer, rng);
        graph.KillMachines(alivePercent);
        results.AddAccessibilitySample(((double)graph.CountUnreachableFrom(0))/((double)n));
        //int minCut = graph.GetMinCut();
        //if(results.minKConnexity == -1 || results.minKConnexity > minCut)
        //results.minKConnexity = minCut;
        //results.UpdateArity(graph);

        // Compute the shortest path
        /*for(int i=0; i<min(graph.size, maxDistanceFrom); i++)
        {
            int distance[graph.size];
            graph.GetDistancesFrom(i, distance);
            results.UpdateDistance(distance, graph.size);
        }*/

        /*int distance[graph.size];
        float routesCount[graph.size];
        int nRefresh = 1;

        graph.GetDistancesFrom(0, distance);
        double moy = 0;
        for(int i=0; i<graph.size; i++)
            moy += distance[i];
        moy /= graph.size;
        cout << "Avg distance : " << moy << endl; cout.flush();

        for(int i = 0; i<100; i++)
        {
            for(int j=0; j<graph.size; j++)
            {
                graph.GetRoutesFrom(j, distance, routesCount);
                unordered_set<int> alreadyConnected;

                // erase some edge
                for(int k=0; k<nRefresh; k++)
                {
                    int minNode = -1;
                    int minimum = -1;
                    for(int index = 0; index < graph.generated[j].size(); index++)
                        if(minNode == -1 || routesCount[graph.generated[j][index]] < minimum)
                        {
                            minNode = graph.generated[j][index];
                            minimum = routesCount[minNode];
                        }

                    graph.RemoveEdge(j, minNode);
                }

                // Add new edges
                alreadyConnected.insert(j);
                for(int k : graph.adjacency[j])
                    alreadyConnected.insert(k);

                for(int k=0; k<nRefresh; k++)
                    alreadyConnected.insert(graph.AddEdge(j, alreadyConnected));
            }

            graph.GetDistancesFrom(0, distance);
            moy = 0;
            for(int i=0; i<graph.size; i++)
                moy += distance[i];
            moy /= graph.size;
            cout << "Avg distance : " << moy << endl;
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
    fprintf(output, "n,k,a,accessibility\n");

    vector<future<string>> outputStrings;
    for(int n=10000; n<=10000; n*=2)
        for(int k=5; k<=15; k+=5)
            for(float a=0.05; a<1; a+=0.05)
            {
                int seed = rng();
                outputStrings.push_back(async(launch::async, [seed, n, k, a]()
                    {
                        Results results = Simulate(seed, n, k, 2.5*k, 10000, a, 100);
                        ostringstream out;
                        out << n << "," << k << "," << a << ","
                            << results.avgAccessibility
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



// To compile : g++ -std=c++0x results.cpp graph.cpp main.cpp -lpthread 
#include "main.h"

void simulate(int size, int k, int maxPeer, int seed, const Latency& latency, const char* outName)
{
	FILE* output = fopen(outName, "wt");
    int fno = fileno(output);
    fprintf(output, "round,alive,unreachable\n");

	mt19937 rng(seed);
	Graph graph(size, k, maxPeer, rng, latency);

	cout << "\r" << 0 << "/" << 300;
    cout.flush();

	for(int i=0; i<300; i++)
	{
		for(float a=0.05; a<1; a+=0.05)
		{
			Graph copy(graph);
			copy.KillMachines(a);
			fprintf(output, "%d,%f,%f\n",i, a , copy.GetUnAvalaibility());
			fflush(output);
        	fsync(fno);
		}
		

		double avgDistance, unreachable;
		double arityDistrib[31];
		graph.UpdateLowRoutes(avgDistance, unreachable, arityDistrib);
    	cout << "\r" << i+1 << "/" << 300;
        cout.flush();
	}

	cout << endl;
    fclose(output);
}

int main(int argc, char** argv)
{
	mt19937 rng(time(NULL));
	//Latency latency("latency/pw-1715/pw-1715-latencies", 1715);
	//latency.Rewrite(20);
	Latency latency("latency/pw-1715/rewrite", 1555);

	vector<future<void>> threads;
	
	for(int i=0; i<8; i++)
	{
		int seed = rng();
		char* out = new char[20];
		sprintf(out, "out_%d.csv", i);
		threads.push_back(async(launch::async, [seed, out, &latency]()
        	{ simulate(1555, 10, 30, seed, latency, out); delete[] out; })); 
	}

	for(int i=0; i<8; i++)
        threads[i].get();

    return 0;
}
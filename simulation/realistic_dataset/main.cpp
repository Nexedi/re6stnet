// To compile : g++ -std=c++0x results.cpp graph.cpp main.cpp -lpthread 
#include "main.h"

void simulate(int size, int k, int maxPeer, int seed, const Latency& latency, const char* outName)
{
	FILE* output = fopen(outName, "wt");
    int fno = fileno(output);
    fprintf(output, "round,avgdistance,unreachable,arity 0..30\n");

	mt19937 rng(seed);
	Graph graph(size, k, maxPeer, rng, latency);

	cout << "\r" << 0 << "/" << 2000;
    cout.flush();

	for(int i=0; i<2000; i++)
	{
		double avgDistance, unreachable;
		double arityDistrib[maxPeer+1];
		graph.UpdateLowRoutes(avgDistance, unreachable, arityDistrib);

		fprintf(output, "%d,%f,%f", i , avgDistance, unreachable);
		for(int j=0; j<=maxPeer; j++)
			fprintf(output, ",%f", arityDistrib[j]);
		fprintf(output, "\n");
        fflush(output);
        fsync(fno);
    
    	cout << "\r" << i+1 << "/" << 2000;
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
	Latency latency("latency/pw-1715/rewrite", 1556);

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
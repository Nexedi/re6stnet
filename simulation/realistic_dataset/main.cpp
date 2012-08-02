// To compile : g++ -std=c++0x latency.cpp graph.cpp main.cpp -lpthread 
// The best distance for latency : 66.9239 with a full graph
// other dataset : http://pdos.csail.mit.edu/p2psim/kingdata/
// for latency_2 :
// Optimal distance : 16085.3
// Average ping : 75809.4

#include "main.h"

void simulate(int size, int k, int maxPeer, int seed, const Latency& latency, const char* outName)
{
	mt19937 rng(seed);

	FILE* output = fopen(outName, "wt");
    int fno = fileno(output);

	Graph graph(size, k, maxPeer, rng, latency);

	cout << "\r" << 0 << "/" << 3000;
    cout.flush();

	for(int i=0; i<3000; i++)
	{
		/*for(float a=0.05; a<1; a+=0.05)
		{
			Graph copy(graph);
			copy.KillMachines(a);
			fprintf(output, "%d,%f,%f\n",i , a , copy.GetUnAvalaibility());
			fflush(output);
        	fsync(fno);
		}*/
		

		double avgDistance, unreachable;
		double arityDistrib[31], bcArity[31];
		graph.Reboot(1.0/(1036.8 + 1.0));
		graph.UpdateLowRoutes(avgDistance, unreachable, arityDistrib, bcArity, 1, i);

		fprintf(output, "%d,%f", i, avgDistance);
		for(int j=0; j<=30; j++)
			fprintf(output, ",%f", arityDistrib[j]);
		for(int j=0; j<=30; j++)
			fprintf(output, ",%f", bcArity[j]);
		fprintf(output, "\n");
		fflush(output);
    	fsync(fno);

    	cout << "\r" << i+1 << "/" << 3000;
        cout.flush();
	}

	cout << endl;
    fclose(output);
}

int main(int argc, char** argv)
{
	mt19937 rng(time(NULL));
	//Latency latencyR("latency/pw-1715/pw-1715-latencies", 1715);
	//latencyR.Rewrite(20);
	Latency latency("datasets/latency_2_2500", 2500);

	//cout << "Optimal distance : " << latency.GetAverageDistance() << endl;
	//cout << "Average ping : " << latency.GetAveragePing() << endl;
	vector<future<void>> threads;
	
	for(int i=0; i<1; i++)
	{
		int seed = rng();
		char* out = new char[20];
		sprintf(out, "out_%d.csv", i);
		threads.push_back(async(launch::async, [seed, out, &latency]()
        	{ simulate(2500, 10, 30, seed, latency, out); delete[] out; })); 
	}

	for(int i=0; i<1; i++)
        threads[i].get();

    return 0;
}

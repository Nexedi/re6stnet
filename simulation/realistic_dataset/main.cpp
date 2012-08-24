// To compile : g++ -std=c++0x latency.cpp graph.cpp main.cpp -lpthread 
// other dataset : http://pdos.csail.mit.edu/p2psim/kingdata/
// for latency_2 :
// Optimal distance : 16085.3
// Average ping : 75809.4

#include "main.h"

void simulate(int size, int k, int maxPeer, int seed, Latency* latency, const char* outName)
{
	mt19937 rng(seed);

	FILE* output = fopen(outName, "wt");
    int fno = fileno(output);
    double nRoutesKilled = 0;
    //int arityKillDistrib[maxPeer+1][10];
    double avgDistance, unreachable;
	double arityDistrib[31], bcArity[31];

	Graph graph(size, k, maxPeer, rng, latency, 0, 0.05);

	cout << "\r" << 0 << "/" << 3000;
    cout.flush();

	for(int i=0; i<3000; i++)
	{
		/*if(i>=100)
		{
			for(float a=0.05; a<1; a+=0.05)
			{
				Graph copy(graph);
				copy.KillMachines(a);
				fprintf(output, "%d,%f,%f\n",i , a , copy.GetUnAvalaibility());
				fflush(output);
	        	fsync(fno);
			}
		}*/
		

		
		//graph.Reboot();
		graph.UpdateLowRoutes(avgDistance, unreachable, nRoutesKilled, arityDistrib, bcArity, 1, i);
		//graph.GetArityKill(arityKillDistrib);

		fprintf(output, "%d,%f,%f", i, avgDistance, nRoutesKilled);
		for(int j=k; j<=30; j++)
			fprintf(output, ",%f", arityDistrib[j]);
		/*fprintf(output, ",B");
		for(int j=k; j<=30; j++)
			fprintf(output, ",%f", bcArity[j]);
		for(int j=0; j<10; j++)
		{
			fprintf(output, ",K%d", j);
			for(int a=k; a<=maxPeer; a++)
				fprintf(output, ",%d", arityKillDistrib[a][j]);
		}*/
		fprintf(output, "\n");
		fflush(output);
    	fsync(fno);

    	cout << "\r" << i+1 << "/" << 3000;
        cout.flush();
	}

	cout << endl;
    fclose(output);
}

void testOptimized(int size, int k, int maxPeer, int seed, Latency* latency, const char* outName)
{
	cout << "\r" << 0 << "/" << 3000;
    cout.flush();

    FILE* output = fopen(outName, "wt");
    int fno = fileno(output);

    FILE* input = fopen("update_order", "r");

	mt19937 rng(seed);
	Graph graph(size, k, maxPeer, rng, latency, 0, 0.1);

	double nRoutesKilled = 0;
	int arityDistrib[maxPeer+1];

    for(int i=0; i<3000; i++)
	{
		int toUpdate;
		fscanf(input, "%d", &toUpdate);

		pair<double, double> result = graph.UpdateLowRoutesArity(toUpdate);

		nRoutesKilled += result.second;

		graph.GetArity(arityDistrib);

    	fprintf(output, "%d,%f,%d,%f,A", i, result.first, toUpdate, nRoutesKilled);
 		for(int a=k; a<=maxPeer; a++)
			fprintf(output, ",%d", arityDistrib[a]);

    	fprintf(output, "\n");
		fflush(output);
    	fsync(fno);

    	graph.Reboot();

    	cout << "\r" << i+1 << "/" << 3000;
    	cout.flush();
	}

	cout << endl;
	fclose(output);
	fclose(input);
}

void Optimize(int size, int k, int maxPeer, int seed, Latency* latency, const char* outName)
{
	cout << "\r" << 0 << "/" << 3000;
    cout.flush();

    FILE* output = fopen(outName, "wt");
    int fno = fileno(output);

	mt19937 rng(seed);
	Graph* graph = new Graph(size, k, maxPeer, rng, latency, 0, 0.1);
	int range = maxPeer - k + 1;

	int updates[range];
	for(int i = 0; i<range; i++)
		updates[i] = 0;

	pair<double, double> results[range];
	Graph* copies[range];

	double oldDistance = numeric_limits<double>::infinity();
	double nRoutesKilled = 0;
	int arityDistrib[maxPeer+1];

    for(int i=0; i<1000; i++)
	{
		vector<future<pair<double, double>>> threads;
		for(int a=0; a<range; a++)
		{
			copies[a] = new Graph(*graph);
			auto lambda = [] (Graph *g, int a, int k) { return g->UpdateLowRoutesArity(a + k); };
			threads.push_back(async(launch::async, lambda, copies[a], a, k));
		}


		int minIndice = 0;
		double minValue = numeric_limits<double>::infinity();

		for(int a=0; a<range; a++)
		{
			results[a] = threads[a].get();
			if(results[a].second > 0)
			{
				double val = (results[a].first - oldDistance)/results[a].second;
				if(val < minValue)
				{
					minIndice = a;
					minValue = val;
				}
			}
		}

		swap(graph,copies[minIndice]);
		for(int a=0; a<range; a++)
			delete copies[a];

		updates[minIndice]++;

		oldDistance = results[minIndice].first;
		nRoutesKilled += results[minIndice].second;
		graph->GetArity(arityDistrib);

    	fprintf(output, "%d,%f,%f,U", i, oldDistance, nRoutesKilled);
    	for(int a=0; a<range; a++)
			fprintf(output, ",%d", updates[a]);
		fprintf(output, ",A");
 		for(int a=0; a<range; a++)
			fprintf(output, ",%d", arityDistrib[a+k]);

    	fprintf(output, "\n");
		fflush(output);
    	fsync(fno);

    	graph->Reboot();

    	cout << "\r" << i+1 << "/" << 3000;cout.flush();
	}

	delete graph;
	cout << endl;
}

string computeDist(int size, int k, int maxPeer, int seed, Latency* latency)
{
	mt19937 rng(seed);
	Graph graph(size, k, maxPeer, rng, latency, 0, 0.1);

	double avgDistLatency = 0;
	int nRoutes[size], prevs[size], distances[size];
	for(int i=0; i<size; i++)
	{
		graph.GetRoutesFrom(i,  nRoutes, prevs, distances);
		for(int j=0; j<size; j++)
			avgDistLatency += distances[j];
	}

	ostringstream out;
    out << avgDistLatency / (size*size) << ","
    	<< graph.GetAvgDistanceHop() << endl;
    return out.str();
}

int main(int argc, char** argv)
{
	mt19937 rng(time(NULL));
	Latency* latency = new Latency("datasets/latency_2_2500", 2500);

	cout << "Optimal distance : " << latency->GetAverageDistance() << endl;
	cout << "Average ping : " << latency->GetAveragePing() << endl;

	vector<future<void>> threads;
	
	for(int i=0; i<4; i++)
	{
		int seed = rng();
		char* out = new char[100];
		sprintf(out, "out_%d.csv", i);
		threads.push_back(async(launch::async, [seed, out, latency]()
        	{ simulate(2500, 10, 30, seed, latency, out); delete[] out; })); 
	}

	for(int i=0; i<4; i++)
        threads[i].get();

	//Optimize(2500, 10, 30, rng(), latency, "out.csv");

	delete latency;
    return 0;
}

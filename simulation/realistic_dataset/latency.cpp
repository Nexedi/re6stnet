#include "main.h"

Latency::Latency(const char* filePath, int size) : size(size)
{
	values = new int*[size];
	avgLatencyToOthers = new double[size];
	for(int i=0; i<size; i++)
	{
		values[i] = new int[size];
		for(int j=0; j<size; j++)
			values[i][j] = -1;
	}


	FILE* file = NULL;
	file = fopen(filePath, "r");
	int a, b;
	double latency;

	while(!feof(file))
	{
		fscanf(file, "%d %d %lf", &a, &b, &latency);
		if(latency < 100)
			latency = -1;

		values[b-1][a-1] = latency;
		values[a-1][b-1] = latency;
	}

	fclose(file);

	for(int i=0; i<size; i++)
	{
		avgLatencyToOthers[i] = 0;
		for(int j=0;j<size; j++)
			avgLatencyToOthers[i] += values[i][j];
		avgLatencyToOthers[i] /= size;
	}

}

void Latency::Rewrite(int n)
{
	int nat[size];
	int nextId = 0;
	for(int i=0; i<size; i++)
	{
		int nReachable = 0;
		for(int j=0; j<size; j++)
		{
			if(j !=  i && values[i][j] >= 10)
				nReachable++;
		}

		if(nReachable <= n)
			nat[i] = -1;
		else
		{
			nat[i] = nextId;
			nextId++;
		}
	}

	FILE* file = NULL;
	file = fopen("latency/pw-1715/rewrite", "w");
	for(int i=0; i<size-1; i++)
		if(nat[i] != -1)
			for(int j=i+1; j<size; j++)
				if(nat[j] != -1)
					fprintf(file, "%d %d %d\n", nat[i], nat[j], values[i][j]>=10?values[i][j]:-1);

	fclose(file);
}

Latency::~Latency()
{
	for(int i=0; i<size; i++)
		delete[] values[i];
	delete[] values;
	delete[] avgLatencyToOthers;
}

double Latency::GetAverageDistance()
{
	int size = 1555;
    double** distances = new double*[size];
    for(int i=0; i<size; i++)
    	distances[i] = new double[size];

	for(int i=0; i<size; i++)
		for(int j=0; j<size; j++)
			if(i==j)
				distances[i][j] = 0;
			else if(values[i][j] > 0)
				distances[i][j] = values[i][j];
			else
				distances[i][j] =  numeric_limits<double>::infinity();

	for(int i=0; i<size; i++)
		for(int j=0; j<size; j++)
			for(int k=0; k<size; k++)
				distances[i][j] = min(distances[i][j], distances[i][k] + distances[k][j]);

	double avg = 0;
	for(int i=0; i<size; i++)
		for(int j=0; j<size; j++)
			avg += distances[i][j];

	return avg / (size*size);
}

double Latency::GetAveragePing()
{
	double out = 0;
	double nPing = 0;
	for(int i=0; i<size; i++)
		for(int j=0; j<size; j++)
			if(values[i][j] > 0)
			{
				nPing++;
				out += values[i][j];
			}

	return out/nPing;
}
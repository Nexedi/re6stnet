#include "main.h"

Latency::Latency(const char* filePath, int size) : size(size)
{
	values = new int*[size];
	for(int i=0; i<size; i++)
		values[i] = new int[size];


	FILE* file = NULL;
	file = fopen(filePath, "r");
	int a, b, latency;

	while(!feof(file))
	{
		fscanf(file, "%d %d %d", &a, &b, &latency);
		values[b][a] = latency;
		values[a][b] = latency;
	}

	fclose(file);
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
			if(values[i][j] > 0)
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
			for(int j=1; j<size; j++)
				if(nat[j] != -1)
					fprintf(file, "%d %d %d\n", nat[i], nat[j], values[i][j]);

	fclose(file);
}

Latency::~Latency()
{
	for(int i=0; i<size; i++)
		delete[] values[i];
	delete[] values;
}
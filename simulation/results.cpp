#include "main.h"

Results::Results(int maxArity, int maxDistance) : 
    maxArity(maxArity), maxDistance(maxDistance)
{
    arityDistrib = new double[maxArity+1];
    for(int i=0; i<=maxArity; i++)
        arityDistrib[i] = 0;

    distanceDistrib = new double[maxDistance+1];
    for(int i=0; i<=maxDistance; i++)
        distanceDistrib[i] = 0;

    nAritySample = 0;
    nDistanceSample = 0;
    arityTooBig = 0;
    distanceTooBig = 0;
    disconnected = 0;
    avgDistance = 0;
    maxDistanceReached = -1;
}

Results::~Results()
{
    delete[] arityDistrib;
    delete[] distanceDistrib;
}

void Results::UpdateArity(const Graph& graph)
{
    for(int i=0; i<graph.size; i++)
        AddAritySample(graph.adjacency[i].size());
}

void Results::UpdateDistance(int* distance, int nSamples)
{
    for(int i=0; i<nSamples; i++)
        AddDistanceSample(distance[i]);
}

void Results::AddAritySample(int arity)
{
    if(arity <= maxArity)
        arityDistrib[arity]++;
    else
        distanceTooBig++;
    nAritySample++;
}

void Results::AddDistanceSample(int distance)
{
    if(distance == -1)
        disconnected++;
    else 
    {
        avgDistance += distance;
        if(distance <= maxDistance)
            distanceDistrib[distance]++;
        else
            distanceTooBig++;
    }
    nDistanceSample++;
    maxDistanceReached = max(maxDistanceReached, distance);
}

void Results::Finalise()
{
    for(int i=0; i<=maxArity; i++)
        arityDistrib[i] /= nAritySample;
    for(int i=0; i<=maxDistance; i++)
        distanceDistrib[i] /= nDistanceSample;
    disconnectionProba = ((double)disconnected)/nDistanceSample;
    distanceTooBig/= nDistanceSample;
    arityTooBig /= nAritySample;
    avgDistance /= nDistanceSample - disconnected;
}

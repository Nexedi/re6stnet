#include "main.h"

Graph::Graph(int size, int k, int maxPeers, mt19937 rng) : 
    distrib(uniform_int_distribution<int>(0, size-1)),
    size(size)
{
    adjacency = new vector<int>[size];
    for(int i=0; i<size; i++)
    {
        set<int> alreadyConnected;
        alreadyConnected.insert(i);

        for(int j=0; j<k; j++)
        {
            int otherNode;

            while(alreadyConnected.count(otherNode = distrib(rng)) == 1 
                || otherNode > i && adjacency[otherNode].size() > maxPeers-10
                || adjacency[otherNode].size() > maxPeers) 
            { }
            adjacency[i].push_back(otherNode);
            adjacency[otherNode].push_back(i);
        }
    }
}

void Graph::GetDistancesFrom(int node, int* distance)
{
    for(int j=0; j<size; j++)
        distance[j] = -1;
    distance[node] = 0;

    queue<int> remainingNodes;
    remainingNodes.push(node);

    while(!remainingNodes.empty())
    {
        int node = remainingNodes.front();
        remainingNodes.pop();

        for(int neighbor : adjacency[node])
            if(distance[neighbor] == -1)
            {
                distance[neighbor] = distance[node]+1;
                remainingNodes.push(neighbor);
            }
    }
}

// kill the last proportion*size machines of the graph
void Graph::KillMachines(float proportion)
{
    // TODO
}

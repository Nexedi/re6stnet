#include "main.h"
#include <cmath>
#include <map>
#include <queue>

Graph::Graph(int size, int k, int maxPeers, mt19937& rng) :
    distrib(uniform_int_distribution<int>(0, size-1)),
    size(size), generator(rng)
{
    adjacency = new vector<int>[size];
    for(int i=0; i<size; i++)
    {
        unordered_set<int> alreadyConnected;
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

int Graph::CountUnreachableFrom(int node)
{
    bool accessibility[size];
    for(int i=0; i<size; i++)
        accessibility[i] = false;
    accessibility[node] = true;
    int unAccessible = size;

    queue<int> toVisit;
    toVisit.push(node);
    while(!toVisit.empty())
    {
        int n = toVisit.front();
        for(int i : adjacency[n])
        {
            if(!accessibility[i])
            {
                toVisit.push(i);
                accessibility[i] = true;
            }
        }

        unAccessible--;
        toVisit.pop();
    }

    return unAccessible;
}

// kill the last proportion*size machines of the graph
void Graph::KillMachines(float proportion)
{
    size = proportion*size;
    for(int i=0; i<size; i++)
    {
        auto it=adjacency[i].begin();
        while(it!=adjacency[i].end())
        {
            if(*it >= size)
                it = adjacency[i].erase(it);
            else
                it++;
        }
    }
}

int Graph::GetMinCut()
{
    int nIter = log(size);
    int minCut = -1;
    for(int i=0; i<nIter; i++)
    {
        MinCutGraph graph = MinCutGraph(adjacency, size);
        int minCutCandidate = GetMinCut(graph);
        if(minCut == -1 || minCut > minCutCandidate)
            minCut = minCutCandidate;
    }

    return minCut;
}

int Graph::GetMinCut(MinCutGraph& copy1)
{
    int n=copy1.nodes.size();

    if(n==2)
        return copy1.edges.size();

    MinCutGraph copy2(copy1);

    int nMerge = min(n-2.0, n/1.414);
    copy1.Merge(nMerge, generator);
    copy2.Merge(nMerge, generator);

    return min(GetMinCut(copy1), GetMinCut(copy2));
}

MinCutGraph::MinCutGraph(vector<int>* adjacency, int n)
{
    nodes.resize(n);
    int nextEdgeId = 0;

    for(int i=0; i<n; i++)
        for(int j : adjacency[i])
            if(j > i)
            {
                nodes[i].v.insert(nextEdgeId);
                nodes[j].v.insert(nextEdgeId);
                edges.push_back(nullable<pair<int, int>>(pair<int, int>(i, j)));
                nextEdgeId++;
            }
}

void MinCutGraph::Merge(int nMerge, mt19937& rng)
{
    uniform_int_distribution<int> distrib(0, edges.size()-1);

    while(nMerge > 0)
    {
        // Choose an edge
        int eId = distrib(rng);
        if(edges[eId].null)
            continue;

        int n1 = edges[eId].v.first;
        int n2 = edges[eId].v.second;

        // anilate n2
        nodes[n2].null = true;

        // redirect all edges from n2
        for(int i : nodes[n2].v)
        {
            if(edges[i].v.first == n1 || edges[i].v.second == n1)
            {
                nodes[n1].v.erase(i);
                edges[i].null = true;
            }

            else
            {
                nodes[n1].v.insert(i);

                if(edges[i].v.first == n2)
                    edges[i].v.first = n1;
                else
                    edges[i].v.second = n1;
            }
        }

        nMerge--;
    }

    RenumNodes();
    RenumEdges();
}

void MinCutGraph::Check()
{
    cout << "CHECKING ... "; cout.flush();
    for(int i=0; i<edges.size(); i++)
    {
        if(!edges[i].null)
        {
            auto e = edges[i].v;

            if(e.first >= nodes.size())
                cout << "Bad first" << endl; cout.flush();
            if(e.second >= nodes.size())
                cout << "Bad second" << endl; cout.flush();
            if(nodes[e.first].v.count(i) == 0)
                cout << "Bad first node" << endl; cout.flush();
            if(nodes[e.second].v.count(i) == 0)
                cout << "Bad second node" << endl; cout.flush();
        }
    }

    for(int i=0; i<nodes.size(); i++)
        if(!nodes[i].null)
            for(int e : nodes[i].v)
                if(edges[e].v.first != i && edges[e].v.second != i)
                    cout << "Bad edge" << endl; cout.flush();

    cout << "DONE" << endl; cout.flush();
}

void MinCutGraph::RenumEdges()
{
    int nextId = 0;
    for(int i=0; i<edges.size(); i++)
        if(!edges[i].null)
        {
            edges[nextId] = edges[i];
            nodes[edges[nextId].v.first].v.erase(i);
            nodes[edges[nextId].v.first].v.insert(nextId);
            nodes[edges[nextId].v.second].v.erase(i);
            nodes[edges[nextId].v.second].v.insert(nextId);
            nextId++;
        }
    edges.resize(nextId);
}

void MinCutGraph::RenumNodes()
{
    int nextId = 0;
    for(int i=0; i<nodes.size(); i++)
        if(!nodes[i].null)
        {
            nodes[nextId] = nodes[i];
            for(int j : nodes[nextId].v)
            {
                if(edges[j].v.first == i)
                    edges[j].v.first = nextId;
                else
                    edges[j].v.second = nextId;
            }
            nextId++;
        }
    nodes.resize(nextId);
}


// To compile with -std=c++0x
// The GET_BC option might not be working
//#define GET_BC // Uncomment this line to get the betweeness centrality
#include "main.h"

int n = 1000; // the number of peer
int k = 10; // each peer try to make k connections with the others
int maxPeer = 25; // no more that 25 connections per peer
int runs = 100;  // use this to run the simulation multiple times to get more accurate values
int betweenessDiv = 20; // to kown how to sample the BC. Max BC should be betweenessDiv*100

Graph::Graph(int size, int k, int maxPeers, mt19937 rng) : 
    distrib(uniform_int_distribution<int>(0, n-1)),
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

int main()
{
    mt19937 rng(time(NULL));

    // Init the parameters
    double array(arityDistrib, maxPeer+1);
    double array(distanceDistrib, n);
    double array(betweenessDistrib, 100);
    int disconnected = 0;

    for(int r=0; r<runs; r++)
    {
        cout << "\r       \rRun " << r;
        cout.flush();

        Graph graph(n, k, maxPeer, rng);
        double array(betweeness, n);

        // Get the arity distribution
        for(int i=0; i<n; i++)
            arityDistrib[graph.adjacency[i].size()]++;

        // Compute the shortest path
        // TODO : optimise this
        // switch to int64 ?
        for(int i=0; i<graph.size; i++)
        {
            int distance[graph.size];
            // if(i%10==0) cout << "Computing distances from node " << i << endl;
            graph.GetDistancesFrom(i, distance);

            // retrieve the distance
            int maxDistance = -1;
            for(int j=0; j<graph.size; j++)
                if(distance[j] != -1)
                {
                    maxDistance = max(distance[j], maxDistance);
                    distanceDistrib[distance[j]]++;
                }
                else
                    disconnected++;

#ifdef GET_BC
            // Get the betweeness
            double toBePushed[graph.size];
            for(int j=0; j<n; j++)
                toBePushed[j] = 1;
          
            // TODO : change this  into a true sort ?
            // run accross the nodes in the right order
            // we don't need to sort them since we will only run across them a few times
            for(int d=maxDistance; d>=0; d--)
                for(int j=0; j<graph.size; j++)
                    if(distance[j] == d)
                    {
                        int nMin, min = -1;
                        for(int neighbor : graph.adjacency[j])
                        {
                            if(distance[neighbor] < min || min == -1)
                            {
                                min = distance[neighbor];
                                nMin = 1;
                            }
                            else if(distance[neighbor] == min)
                                nMin++;
                        }
                        
                        double singleScore = toBePushed[j]/nMin;
                        for(int neighbor : graph.adjacency[j])
                            if(distance[neighbor] == min)
                                toBePushed[neighbor] += singleScore;
                      
                        betweeness[j] += toBePushed[j] - 1;
                    }
#endif
        }
#ifdef GET_BC
        // Get the betweeness distribution
        for(int i=0; i<n; i++)
            betweenessDistrib[min((int)betweeness[i]/betweenessDiv, 99)]++;
#endif
    }
    cout << "\r            \r";

    // Display the parameters we have mesured
    cout << "Arity :" << endl;
    for(int i=0; i<=maxPeer; i++)
        if(arityDistrib[i] != 0)
        {
            arityDistrib[i] /= (double)(n*runs);
            cout << i << " : " << arityDistrib[i] << endl;
        }
    
    cout << "Distance :" << endl;
    double nLinks = n*(n-1)*runs;
    for(int i=0; i<n; i++)
        if(distanceDistrib[i] != 0)
        {
            distanceDistrib[i] /= nLinks - disconnected;
            cout << i << " : " << distanceDistrib[i] << endl;
        }
    
    cout << "Probability that a node is not reachable : " 
         << disconnected/nLinks 
         << " (" << disconnected << " total)" << endl;

#ifdef GET_BC
    cout << "Betweeness :" << endl;
    double nNodes = n*runs;
    for(int i=0; i<100; i++)
        if(betweenessDistrib[i] != 0)
            cout << betweenessDiv*i << " -> " << betweenessDiv*(i+1) << " : " 
                 << betweenessDistrib[i]/nNodes << endl;
#endif

    cout << endl;
    return 0;
}



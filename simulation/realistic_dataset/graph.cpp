#include "main.h"

Graph::Graph(int size, int k, int maxPeers, mt19937& generator,  const Latency& latency) :
	generator(generator), size(size), k(k), maxPeers(maxPeers), latency(latency),
	distrib(uniform_int_distribution<int>(0, size-1))
{
	adjacency = new unordered_set<int>[size];
	generated = new unordered_set<int>[size];

	for(int i=0; i<size; i++)
		SaturateNode(i);
}

Graph::Graph(const Graph& g) :
	generator(g.generator), size(g.size), k(g.k), maxPeers(g.maxPeers), latency(latency),
	distrib(g.distrib)
{
	adjacency = new unordered_set<int>[size];
	generated = new unordered_set<int>[size];

	for(int i=0; i<size; i++)
	{
		adjacency[i] = unordered_set<int>(g.adjacency[i]);
		generated[i] = unordered_set<int>(g.generated[i]);
	}
}

void Graph::SaturateNode(int node)
{
	while(generated[node].size() < k && AddEdge(node)) { }
}

bool Graph::AddEdge(int from)
{
	int to;
	for(int i=0; i<50; i++)
	{
		to = distrib(generator);
		if(latency.values[from][to] > 0
			&& to != from
			&& adjacency[from].count(to) == 0
			&& adjacency[to].size() + generated[to].size() <= maxPeers + k)
		{
			generated[from].insert(to);
			adjacency[from].insert(to);
			adjacency[to].insert(from);
			return true;
		}
	}

	//cout << "Warning : a link could not be established from " << from << endl;
	return false;
}

void Graph::RemoveEdge(int from, int to)
{
	generated[from].erase(to);
	adjacency[from].erase(to);
	adjacency[to].erase(from);
}

void Graph::GetRoutesFrom(int from,  int* nRoutes, int* prevs, int* distances)
{
	// init vars
    stack<int> order;

    for(int i=0; i<size; i++)
    {
        distances[i] = -1;
        nRoutes[i] = 1;
    }
    distances[from] = 0;

    priority_queue<pair<int, int>> remainingNodes;
    remainingNodes.push(pair<int, int>(-0, from));

    // Get the order
    while(!remainingNodes.empty())
    {
    	pair<int, int> p = remainingNodes.top();
        int node = p.second;
        int d = -p.first;
        remainingNodes.pop();

        if(d == distances[node])
        {
	        order.push(node);
	        for(int neighbor : adjacency[node])
	        {
	        	int neighborDist = d + latency.values[neighbor][node];

	            if(distances[neighbor] == -1 || distances[neighbor] > neighborDist)
	            {
	                distances[neighbor] = neighborDist;
	                prevs[neighbor] = node;
	                remainingNodes.push(pair<int, int>(-neighborDist, neighbor));
	            }
	        }
	    }
    }

    // get the BC
    // The error is here
    while(!order.empty())
    {
        int node = order.top();
        order.pop();
        if(distances[node] != -1 && node != from)
        	nRoutes[prevs[node]] += nRoutes[node];
    }
}


void Graph::UpdateLowRoutes(double& avgDistance, double unreachable, double* arityDistrib)
{
	routesResult results[size];

	for(int i=0; i<size; i++)
	{
    	// Compute the routes
        int nRoutes[size], prevs[size], distances[size];
        GetRoutesFrom(i, nRoutes, prevs, distances);

        // Get the values
        routesResult r;
        r.toDelete = -1;
		for(int j : generated[i])
			if(r.toDelete == -1 || nRoutes[r.toDelete] > nRoutes[j])
				r.toDelete = j;

		r.arity = adjacency[i].size();

		r.avgDistance = 0;
		r.unreachable = 0;
		for(int j=0; j<size; j++)
		{
			if(distances[i] >= 0)
				r.avgDistance += distances[j];
			else
				r.unreachable++;
		}

		r.avgDistance /= (double)(size - r.unreachable);

		results[i] = r;
	}

	avgDistance = 0;
	double avgDistanceWeight = 0;
	unreachable = 0;
	for(int i=0; i<=maxPeers; i++)
		arityDistrib[i] = 0;

	for(int i = 0; i<size; i++)
	{
		//cout << "["; cout.flush();

		routesResult r = results[i];
		if(r.toDelete >= 0)
			RemoveEdge(i, r.toDelete);

		//cout << "#"; cout.flush();

		SaturateNode(i);

		//cout << "]"; cout.flush();

		avgDistance += r.avgDistance*(size-r.unreachable);
		avgDistanceWeight += size-r.unreachable;
		unreachable += r.unreachable;
		arityDistrib[adjacency[i].size()]++;

	}

	avgDistance /= avgDistanceWeight;

	for(int i=0; i<=maxPeers; i++)
		arityDistrib[i] /= size;
}

int Graph::CountUnreachableFrom(int node)
{
    bool accessibility[size];
    for(int i=0; i<size; i++)
        accessibility[i] = false;
    accessibility[node] = true;
    int unreachable = size;

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

        unreachable--;
        toVisit.pop();
    }

    return unreachable;
}

double Graph::GetUnAvalaibility()
{
	double moy = 0;
	for(int i=0; i<size; i++)
		moy += CountUnreachableFrom(i);
	return moy / (size*size);
}

void Graph::KillMachines(float proportion)
{
    size = proportion*size;
    for(int i=0; i<size; i++)
    {
    	vector<int> toBeRemoved;
    	for(int j : adjacency[i])
    		if(j >= size)
    			toBeRemoved.push_back(j);

        for(int j : toBeRemoved)
        {
        	generated[i].erase(j);
        	adjacency[i].erase(j);
        }
    }
}
"""
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
This file is part of the implementation of an algorithm for solving the
3-dimensional case picking problem. A newly considered problem of operational
research that combines the routing of pickers into the warehouse, with the
positioning of 3-dimensional items inside pallets (i.e., Pallet Loading Problem).

The algorithm proposed and implemented comes from a collaboration between the
Department of Engineering at University of Parma (Parma, ITALY) and the
IN3 Computer Science Dept. at Universitat Oberta de Catalunya (Barcelona, SPAIN).


Written by Mattia Neroni Ph.D., Eng. in July 2021.
Author' contact: mattianeroni93@gmail.com
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
"""
import collections
import operator
import random
import itertools
import matplotlib.pyplot as plt
import time
from math import log

from packing import dubePacker
from packing import Pallet
import utils


# Convention value used to obtain a greedy behaviour from the
# Biased Randomised Algorithm implemented below.
# Theorically speaking the value should be as close as possible to 1.
# We have reason to believe an approximation to four decimals should
# be accurate enough.
GREEDY_BETA = 0.9999


def _bra (array, beta):
    """
    This method carry out a biased-randomised selection over a certain list.
    The selection is based on a quasi-geometric function:

                    f(x) = (1 - beta) ^ x

    and it therefore prioritise the first elements in list.

    :param array: <list> The set of options already sorted from the best to the worst.
    :param beta: <float> The parameter of the quasi-geometric distribution.
    :return: The element picked at each iteration.

    """
    arr = list(array)
    L = len(array)
    for _ in range(L):
        idx = int(log(random.random(), 1.0 - beta)) % len(arr)
        yield arr.pop(idx)



class Solver (object):
    """
    An instance of this class represents a solver for the
    3-dimensional Case Picking problem.
    """
    def __init__(self, orderlines, edges, dists, pallet_size=(120,80,150), pallet_max_weight=450):
        """
        :attr orderlines: <tuple<OrderLine>> The set of orderlines for which
                        the problem must be solved.
        :attr edges: <tuple<Edge>> The edges connecting location to each other.
        :attr dists: <numpy.array> The matrix of distances between locations.
        :attr pallet_size: <tuple<int>> Pallets size
        :attr pallet_max_weight: <int> Pallets max weight
        :attr history: The evelution of the best solution during the iterations
                        of the algorithm.

        NOTE that to each OrderLine is supposed to be associated one and only
        one location.
        """
        self.orderlines = orderlines
        self.edges = edges
        self.dists = dists
        self.pallet_size = pallet_size
        self.pallet_max_weight = pallet_max_weight
        self.history = collections.deque()


    def plot (self):
        """
        This method plots the evolution of the current best solution during the
        execution of the algorithm.
        """
        plt.plot(self.history)
        plt.xlabel("Iterations")
        plt.ylabel("Total Distance")
        plt.show()


    def heuristic (self, beta):
        """
         This method provides a single solution to the problem.

         :param beta: <float> The parameter of the quasi-geometric distribution
                    used by the biased randomised selection.
         :return: The resulting list of pallets.

        """
        # Get pallets characteristics on stack
        pallet_size, pallet_max_weight = self.pallet_size, self.pallet_max_weight
        # Build a dummy solution
        palletsList = []
        for orderline in self.orderlines:
            p = Pallet(pallet_size, pallet_max_weight)
            done, packedCases, layersMap = dubePacker(p, orderline)
            assert done == True
            p.cases, p.layersMap = packedCases, layersMap
            p.weight = orderline.weight
            p.volume = orderline.volume
            orderline.pallet = p
            p.orderlines.add(orderline)
            palletsList.append(p)

        # Generate the savings list
        savingsList = sorted(self.edges, key=operator.attrgetter("saving"), reverse=True)

        # Merging process
        for edge in _bra(savingsList, beta):
            # Picks an edge and read the pallet it could connect
            host = edge.origin.pallet
            hosted = edge.end.pallet
            # The the hosting pallet and the hosted pallet are the same the procedure
            # interrupts and goes to the next edge
            if host == hosted:
                continue
            # Control the volumetric lower bound
            if host.volume + hosted.volume > host.maxVolume:
                continue
            # Control the weight lower bound
            if host.weight + hosted.weight > host.maxWeight:
                continue
            # Try merging
            done, packedCases, layersMap = dubePacker(host, hosted)
            if done:
                host.cases = packedCases
                host.layersMap = layersMap
                host.weight += hosted.weight
                host.volume += hosted.volume
                host.orderlines.update(hosted.orderlines)
                palletsList.remove(hosted)
                for line in hosted.orderlines:
                    line.pallet = host
                continue
            # Eventually try a merging using the inverse of the edge -- i.e., switching
            # the hositng pallet with the hosted pallet.
            host, hosted = hosted, host
            done, packedCases, layersMap = dubePacker(host, hosted)
            if done:
                host.cases = packedCases
                host.layersMap = layersMap
                host.weight += hosted.weight
                host.volume += hosted.volume
                host.orderlines.update(hosted.orderlines)
                palletsList.remove(hosted)
                for line in hosted.orderlines:
                    line.pallet = host

        # At the end, return the palletsList
        return palletsList


    @staticmethod
    def getCost(solution, dists):
        """
        Given a solution (a set of pallets) and the matrix of distances, this method calculates
        the cost of the solution -- i.e., the distance walked by the picker to collect all
        cases and construct the pallets.

        :param solution: The set of pallets
        :param dists: The matrix of distances between locations
        :return: The distance walked by the picker to construct all pallets.

        """
        total = 0
        for pallet in solution:
            sort_orderlines = tuple(dict(sorted(pallet.layersMap.items(), key=operator.itemgetter(1))).keys())
            total += dists[0, sort_orderlines[0].location] + dists[sort_orderlines[-1].location, 0]
            total += sum(dists[i.location, j.location] for i, j in zip(sort_orderlines[:-1], sort_orderlines[1:]))
        return total


    def __call__ (self, maxtime, betarange=(0.1, 0.3)):
        """
         This method executes many times the heuristic method generating many
         different solutions until the available time (i.e., maxtime) is not exceeded.
         Every time a new solution is generated, it is compared with the best found so
         far, and, if better, the best solution is temporarily updated.

         :param maxtime: <time>/<float> The available computational time.
         :return: <tuple> It returns (i) the best solution found (a set of pallets),
                    (ii) the cost of the best solution (the distance made by the picker),
                    (iii) the number of solutions explored by the algorithm in the
                    available computational time.

        """
        # Move useful data to the stack
        heuristic = self.heuristic
        getCost = self.getCost
        dists = self.dists
        orderlines = self.orderlines
        save = self.history.append
        # Generate a starting solution
        best = heuristic(GREEDY_BETA)
        bestcost = getCost(best, dists)
        # Start a multistart iterated local search
        iterations = 0
        start = time.time()
        while time.time() - start < maxtime:
            iterations += 1
            # Generate a new solution
            beta = random.uniform(*betarange)
            newsol = heuristic(beta)
            newcost = getCost(newsol, dists)

            # Eventually update the best
            if newcost < bestcost:
                best, bestcost = newsol, newcost
            # Save the current best
            save(bestcost)

        return best, bestcost, iterations

    def sequential (self):
        """
        This method provides a single solution to the problem
        by using a sequential approach --i.e., first the packing optimisation
        is carried out, and then the routing improvement is done.

        This is used to compare the proposed procedure in the __call__ method
        with a different approach where routing and packing are not solved together.
        """
        pallet_size, pallet_max_weight = self.pallet_size, self.pallet_max_weight
        palletsList = []
        # First build a pallet for each orderline (dummy solution)
        for orderline in self.orderlines:
            p = Pallet(pallet_size, pallet_max_weight)
            done, packedCases, layersMap = dubePacker(p, orderline)
            assert done == True
            p.cases, p.layersMap = packedCases, layersMap
            p.weight = orderline.weight
            p.volume = orderline.volume
            orderline.pallet = p
            p.orderlines.add(orderline)
            palletsList.append(p)

        # Sort palletsList for decreasing strength
        palletsList.sort(key=lambda i: i.cases[0].strength, reverse=True)

        # For each couple of different pallets...
        for iPallet, jPallet in itertools.permutations(palletsList, 2):
            # If both are active (have not been merged into others).
            if iPallet.active and jPallet.active:
                # Control the volumetric lower bound
                if iPallet.volume + jPallet.volume > iPallet.maxVolume:
                    continue
                # Control the weight lower bound
                if iPallet.weight + jPallet.weight > iPallet.maxWeight:
                    continue
                # Try merging
                done, packedCases, layersMap = dubePacker(iPallet, jPallet)
                if done:
                    iPallet.cases = packedCases
                    iPallet.layersMap = layersMap
                    iPallet.weight += jPallet.weight
                    iPallet.volume += jPallet.volume
                    iPallet.orderlines.update(jPallet.orderlines)
                    jPallet.active = False
                    for line in jPallet.orderlines:
                        line.pallet = iPallet
        # Remove non-active pallets
        palletsList = list(filter(operator.attrgetter("active"), palletsList))
        return palletsList

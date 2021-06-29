from sympy import *

def readCFG(cfg, recurlist):
    """Takes in a dot file, and extracts a list of two entry lists, each of which
    represents an edge in the control flow graph. This list, as well as the recurlist
    are passed into calculateSystem."""
    f = open(cfg, "r")
    edgelist = []
    for x in f:
        start = ""
        end = ""
        startDone = False
        for char in x:
            if char.isdigit():
                if startDone:
                    end += char
                else:
                    start += char
            else:
                startDone = True
        if end != "": #ignore lines that don't give edges
            edgelist += [[int(start), int(end)]]
    f.close()
    return calculateSystem(edgelist, recurlist)


def calculateSystem(edgelist, recurlist):
    """Takes in a list of all edges in a graph, and a list of where recursive calls are
    located, and creates a system of equations in the form of a dictionary"""
    edgedict = {}
    for edge in edgelist: #reformatting our list of edges into a dictionary where keys are edge starts, and values are lists of edge ends
        startnode = str(edge[0])
        if startnode in edgedict:
            endnodes = edgedict[startnode] + [edge[1]]
        else:
            endnodes = [edge[1]]
        edgedict[startnode] = endnodes
    system = []
    x = symbols('x')
    firstnode = symbols(chr(edgelist[0][0] + 65))
    recurexpr = firstnode*x
    symbs = []
    for startnode in edgedict.keys():
        endnodes = edgedict[startnode]
        expr = Integer(0)
        sym = symbols(chr(int(startnode) + 65))
        symbs += [sym]
        for node in endnodes:
            if str(node) in edgedict.keys(): #makes sure the end node is not terminal
                var = symbols(str(chr(node+ 65)))
                expr = expr + var*x
            else:
                expr = expr + x
            expr = (recurexpr**recurlist[int(startnode)]) * expr #recursion
        system += [expr - sym]
    print(system)

    solutions = nonlinsolve(system, symbs)
    ret = []
    for i in solutions.args:
        ret += [i[0]]

    return ret
recurlist = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
#print(calculateSystem(edgelist, recurlist))

print(readCFG("/home/elip/metrinome/src/tests/dotFiles/vlab_cs_ucsb_test_SimpleExample_test3_0_basic.dot", recurlist))

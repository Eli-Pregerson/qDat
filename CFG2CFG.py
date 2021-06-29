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
    system = {}
    for startnode in edgedict.keys(): #not recursive part of our system of equations
        endnodes = edgedict[startnode]
        eq = ""
        for node in endnodes:
            if str(node) in edgedict.keys():
                eq += " + " + str(chr(node+ 65)) + "x"
            else:
                eq += " + " + "x"
        system[chr(int(startnode) + 65)] = eq[3:]
    firstnode = chr(edgelist[0][0] + 65)
    for i in range(len(recurlist)): #recursive part of our system of equations
        if recurlist[i] > 0:
            recurnode = chr(i + 65)
            if recurlist[i] == 1:
                system[recurnode] = firstnode + "x(" + system[recurnode] + ")"
            else:
                pow = str(recurlist[i])
                system[recurnode] = firstnode + "^(" + pow + ")x^(" + pow + ")(" + system[recurnode] + ")"
    return system
recurlist = [0, 0, 0, 1, 0, 0, 0]
#print(calculateSystem(edgelist, recurlist))
print(readCFG("/home/elip/metrinome/src/tests/dotFiles/vlab_cs_ucsb_test_SimpleExample_test3_0_basic.dot", recurlist))

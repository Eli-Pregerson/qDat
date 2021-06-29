def recursion(num):
    vals = []
    for loop in range(num): #each value of n
        if loop == 0:
            vals += [1]
        else:
            sum = 0
            allLists = []
            for j in range(loop): #how many loops
                numloops = j + 1
                points = loop - numloops
                allLists += recurlists(numloops, points)
            for list in allLists:
                val = 1
                for entry in list:
                    val = val * vals[entry]
                sum += val
            vals += [sum]
            print(sum)
    return vals

def recurlists(numloops, points):
    if numloops == 1:
        return [[points]]
    else:
        l = []
        for i in range(points + 1):
            sublist = recurlists(numloops - 1, points - i)
            newList = []
            for entry in sublist:
                newList += [[i] + entry]
            l += newList
        return l
print(recursion(1000))

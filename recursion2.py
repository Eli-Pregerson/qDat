def recursion(num, dict, start):
    inLanguage = getLang(num, dict, start)
    returnlist = [0] * (num + 1)
    for str in inLanguage:
        returnlist[len(str)] += 1
    return returnlist

def getLang(num, dict, current):
    done = True
    for char in current:
        if char in dict:
            done = False
    if done:
        return [current]
    elif len(current) <= num:
        nextStrings = getNextStrings(dict, current)
        returnlist = []
        for str in nextStrings:
            returnlist += getLang(num, dict, str)
        return returnlist
    else:
        return []

def getNextStrings(dict, current):
    returnlist = [""]
    for char in current:
        if char in dict:
            options = dict[char].split("|")
            tempList = []
            for option in options:
                for str in returnlist:
                    tempList += [str + option]
            returnlist = tempList
        else:
            tempList = []
            for str in returnlist:
                tempList += [str + char]
            returnlist = tempList
    return returnlist

dict = {}
dict["x"] = "1s"
dict["s"] = "2t|4"
dict["t"] = "1s3r"
dict["r"] = "1s"
start = "x"
for i in range(999):
    val = recursion(i, dict, start)[i]
    if val > 0:
        print(val)

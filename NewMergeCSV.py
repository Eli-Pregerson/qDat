# Author: Aditya Bhargava (abhargava@g.hmc.edu)
# Date: Summer 2021
# Organization: HMC ALPQAQ REU
# Takes in an already merged file with source code, process metrics, and Metrinome metrics and returns them in a combined file called 'AllMetrics10Fold.csv
import csv
base_path = '/Users/adityabhargava/Desktop/ALPAQA/'
clean_by = 0

def mergeCSVTenFold():
    sourceCodeFields = 'ID', 'method', 'fanIN', 'fanOUT', 'localVar', 'parametersCount', 'commentToCodeRatio', 'countPath', 'complexity', 'execStmt', 'maxNesting', 'readability', 'cos', 'Purpose', 'Notice', 'UnderDev', 'StyleAndIde', 'Metadata', 'Discarded', 'featureEnvy', 'longParam', 'messageChains', 'longMethod'
    changeMetricsFields = 'methodHistories', 'authors', 'stmtAdded', 'maxStmtAdded', 'avgStmtAdded', 'stmtDeleted', 'maxStmtDeleted', 'avgStmtDeleted', 'churn', 'maxChurn', 'avgChurn', 'decl', 'cond', 'elseAdded', 'elseDeleted', 'developers', 'ownership', 'entropy'
    metrinomeMetricsFields = 'APC type', 'APC exp coeff', 'APC exp base', 'APC poly coeff', 'APC poly power'
    booleanField = 'buggy', 

    with open(base_path + 'projects_to_merge.txt', 'r', newline='', encoding="utf-8") as projects:
        for project in projects:
            project = project.strip()
            print("Working on: " + project)
            # Merge releases in unique file for 10 fold cross validation on all history
            # "w" will create if the specified file DNE
            with open(base_path + 'output/' + project + '/AllMetrics10Fold.csv', 'w', newline='', encoding="utf-8") as allMetricsCleanedCsv:
                allFields = sourceCodeFields + changeMetricsFields + metrinomeMetricsFields+booleanField
                allMetricsCleaned = csv.DictWriter(allMetricsCleanedCsv, delimiter=',', fieldnames=allFields)
                allMetricsCleaned.writeheader()

                releases = csv.DictReader(open(base_path + 'output/' + project + '_releases.csv', 'r', encoding="utf-8"), delimiter=',')
                for release in releases:
                    releaseNumber = release['ID']
                    if releaseNumber != '0':
                        print('Working on: ' + project + ' ' + release['ID'])

                        Metrics = csv.DictReader(open(base_path+'output/'+project+'/'+'metrics_'+releaseNumber+'.csv', 'r', encoding = "utf-8"), delimiter = ",")
                        Dict = {}
                        for row in Metrics:
                            Dict[row['method']] = row
                            allMetricsCleaned.writerow(row)

if __name__ == '__main__':
    print("*** Merge CSV - Main app started ***\n")
    mergeCSVTenFold()
    print("\n*** Merge CSV - Main app finished ***")

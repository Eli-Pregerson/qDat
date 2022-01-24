package methodLevelBugPrediction;

import java.io.File;
import java.io.FileNotFoundException;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map.Entry;
import java.util.Random;
import java.util.Scanner;
import java.util.Vector;

import methodLevelBugPrediction.utilities.FileUtilities;
import weka.attributeSelection.AttributeEvaluator;
import weka.attributeSelection.AttributeSelection;
import weka.attributeSelection.CfsSubsetEval;
import weka.attributeSelection.GreedyStepwise;
import weka.attributeSelection.InfoGainAttributeEval;
import weka.attributeSelection.Ranker;
import weka.classifiers.Classifier;
import weka.classifiers.Evaluation;
import weka.classifiers.bayes.BayesNet;
import weka.classifiers.bayes.NaiveBayes;
import weka.classifiers.functions.Logistic;
import weka.classifiers.functions.MultilayerPerceptron;
import weka.classifiers.functions.SMO;
import weka.classifiers.functions.SimpleLogistic;
import weka.classifiers.meta.AttributeSelectedClassifier;
import weka.classifiers.rules.DecisionTable;
import weka.classifiers.trees.J48;
import weka.classifiers.trees.RandomForest;
//import weka.classifiers.trees.ADTree;
import weka.core.Attribute;
import weka.core.Instances;
import weka.core.converters.ConverterUtils;
import weka.filters.Filter;
import weka.filters.supervised.attribute.AddClassification;
import weka.filters.supervised.instance.ClassBalancer;
import weka.filters.unsupervised.attribute.Remove;

public class EvaluateModels {

    private static String output = "project-name,classifier,model-name,TP,FP,FN,TN,accuracy,precision,recall,f-measure,auc-roc,mcc,readability,cos,Purpose,Notice,UnderDev,StyleAndIde,Metadata,Discarded\n";
    private static String output10Fold = "project-name,classifier,model-name,TP,FP,FN,TN,accuracy,precision,recall,f-measure,auc-roc,mcc\n";
    private static String projectName = "";

    private static String basePath = "/Users/adityabhargava/desktop/ALPAQA/";
    private static Integer cleanedBy = 0;

    public static void main(String[] args) {
        HashMap<String, Classifier> classifiers = new HashMap<String, Classifier>();
        /// classifiers.put("SimpleLogistic", new SimpleLogistic());
        /// classifiers.put("MultilayerPerceptron", new MultilayerPerceptron());
        // classifiers.put("ADTree", new ADTree());
        classifiers.put("RandomForest", new RandomForest());
        classifiers.put("Bayesian Network", new BayesNet());
        classifiers.put("Support Vector Machine", new SMO());
        classifiers.put("J48", new J48());
        //
        /// classifiers.put("NaiveBayes", new NaiveBayes());
        /// classifiers.put("Logistic", new Logistic());
        /// classifiers.put("DecisionTable", new DecisionTable());

        try {
            Vector<String> projects = readProjects(basePath + "projects_to_classify.txt");
            for (String project : projects) {
                System.out.println("Working on project " + project);

                // // Input file
                // String project10Fold = basePath + "output/" + project + "/AllMetrics10Fold.csv";
                //
                // System.out.println("Evaluating 10Fold for " + project10Fold);
                // // Load Training and Test set from CSV file
                // Instances instances10Fold = EvaluateModels.readFile(project10Fold);
                //
                // Instances productModel = EvaluateModels.selectProductFeaturesOnly(instances10Fold);
                // Instances productProcessModel = EvaluateModels.selectProductProcessFeaturesOnly(instances10Fold);
                // Instances productProcessTextualModel = EvaluateModels.selectProductProcessTextualFeaturesOnly(instances10Fold);
                // Instances productProcessTextualSmellModel = EvaluateModels.selectProductProcessTextualSmellFeaturesOnly(instances10Fold);
                // Instances productProcessTextualSmellDeveloperRelatedModel = EvaluateModels.selectAllFeatures(instances10Fold);
                //
                //// Instances onlyStructuralModel = EvaluateModels.selectStructuralFeaturesOnly(instances10Fold);
                //// Instances onlyChangeModel = EvaluateModels.selectChangeFeaturesOnly(instances10Fold);
                //// Instances onlyCommentModel = EvaluateModels.selectCommentFeaturesOnly(instances10Fold);
                //// Instances structuralAndChangeModel = EvaluateModels.selectStructuralAndChangeFeaturesOnly(instances10Fold);
                //// Instances structuralAndComment = EvaluateModels.selectStructuralAndCommentFeaturesOnly(instances10Fold);
                //// Instances changeAndComment = EvaluateModels.selectChangeAndCommentFeaturesOnly(instances10Fold);
                //// Instances allModel = EvaluateModels.selectAllFeatures(instances10Fold);
                //
                // for (Entry<String, Classifier> entry : classifiers.entrySet()) {
                // EvaluateModels.evaluateModel10Fold(entry.getValue(), productModel, "productModel", entry.getKey());
                // EvaluateModels.evaluateModel10Fold(entry.getValue(), productProcessModel, "productProcessModel", entry.getKey());
                // EvaluateModels.evaluateModel10Fold(entry.getValue(), productProcessTextualModel, "productProcessTextualModel", entry.getKey());
                // EvaluateModels.evaluateModel10Fold(entry.getValue(), productProcessTextualSmellModel, "productProcessTextualSmellModel", entry.getKey());
                // EvaluateModels.evaluateModel10Fold(entry.getValue(), productProcessTextualSmellDeveloperRelatedModel, "allModel", entry.getKey());
                //
                //// EvaluateModels.evaluateModel10Fold(entry.getValue(), onlyStructuralModel, "structuralModel", entry.getKey());
                //// EvaluateModels.evaluateModel10Fold(entry.getValue(), onlyChangeModel, "changeModel", entry.getKey());
                //// EvaluateModels.evaluateModel10Fold(entry.getValue(), onlyCommentModel, "commentModel", entry.getKey());
                //// EvaluateModels.evaluateModel10Fold(entry.getValue(), structuralAndChangeModel, "structuralAndChangeModel", entry.getKey());
                //// EvaluateModels.evaluateModel10Fold(entry.getValue(), structuralAndComment, "structuralAndCommentModel", entry.getKey());
                //// EvaluateModels.evaluateModel10Fold(entry.getValue(), changeAndComment, "changeAndCommentModel", entry.getKey());
                //// EvaluateModels.evaluateModel10Fold(entry.getValue(), allModel, "allModel", entry.getKey());
                // }

                System.out.println("Evaluating release-by-release for " + project);
                Vector<String> releases = readReleases(basePath + "output/" + project + "_releases.csv");
                for (int i = 1; i < releases.size() - 1; i++) {
                    // if (!project.isHidden()) {
                    String trainingSet = basePath + "output/" + project + "/" + releases.get(i) + "_allMetricsCleaned" + cleanedBy + ".csv";
                    String testSet = basePath + "output/" + project + "/" + releases.get(i + 1) + "_allMetricsCleaned" + cleanedBy + ".csv";

                    System.out.println("Evaluating " + releases.get(i) + "/" + (releases.size() - 1) + " ===> " + trainingSet);

                    // Load Training and Test set from CSV file
                    Instances originTraining = EvaluateModels.readFile(trainingSet);
                    System.out.println(trainingSet);
                    System.out.println(testSet);
                    Instances originTest = EvaluateModels.readFile(testSet);

                    // EvaluateModels.projectName = trainingSet.substring(trainingSet.lastIndexOf("/") + 1, trainingSet.length());
                    EvaluateModels.projectName = project;

                    Instances productTraining = EvaluateModels.selectProductFeaturesOnly(originTraining);
                    Instances processTraining = EvaluateModels.selectProcessFeaturesOnly(originTraining);
                    Instances productProcessTraining = EvaluateModels.selectProductProcessFeaturesOnly(originTraining);
                    Instances textualTraining = EvaluateModels.selectTextualFeaturesOnly(originTraining);
                    Instances productProcessTextualTraining = EvaluateModels.selectProductProcessTextualFeaturesOnly(originTraining);
                    Instances smellTraining = EvaluateModels.selectSmellFeaturesOnly(originTraining);
                    Instances productProcessTextualSmellTraining = EvaluateModels.selectProductProcessTextualSmellFeaturesOnly(originTraining);
                    Instances devRelTraining = EvaluateModels.selectDevRelFeaturesOnly(originTraining);
                    Instances allTraining = EvaluateModels.selectAllFeatures(originTraining);

                    Instances productTest = EvaluateModels.selectProductFeaturesOnly(originTest);
                    Instances processTest = EvaluateModels.selectProcessFeaturesOnly(originTest);
                    Instances productProcessTesting = EvaluateModels.selectProductProcessFeaturesOnly(originTest);
                    Instances textualTest = EvaluateModels.selectTextualFeaturesOnly(originTest);
                    Instances productProcessTextualTestign = EvaluateModels.selectProductProcessTextualFeaturesOnly(originTest);
                    Instances smellTest = EvaluateModels.selectSmellFeaturesOnly(originTest);
                    Instances productProcessTextualSmellTesting = EvaluateModels.selectProductProcessTextualSmellFeaturesOnly(originTest);
                    Instances devRelTest = EvaluateModels.selectDevRelFeaturesOnly(originTest);
                    Instances allTesting = EvaluateModels.selectAllFeatures(originTest);

                    // Instances onlyStructuralModelTraining = EvaluateModels.selectStructuralFeaturesOnly(originTraining);
                    // Instances onlyChangeModelTraining = EvaluateModels.selectChangeFeaturesOnly(originTraining);
                    // Instances onlyCommentModelTraining = EvaluateModels.selectCommentFeaturesOnly(originTraining);
                    // Instances structuralAndChangeModelTraining = EvaluateModels.selectStructuralAndChangeFeaturesOnly(originTraining);
                    // Instances structuralAndCommentTraining = EvaluateModels.selectStructuralAndCommentFeaturesOnly(originTraining);
                    // Instances changeAndCommentTraining = EvaluateModels.selectChangeAndCommentFeaturesOnly(originTraining);
                    // Instances allModelTraining = EvaluateModels.selectAllFeatures(originTraining);
                    //
                    // Instances onlyStructuralModelTest = EvaluateModels.selectStructuralFeaturesOnly(originTest);
                    // Instances onlyChangeModelTesting = EvaluateModels.selectChangeFeaturesOnly(originTest);
                    // Instances onlyCommentModelTestign = EvaluateModels.selectCommentFeaturesOnly(originTest);
                    // Instances structuralAndChangeModelTesting = EvaluateModels.selectStructuralAndChangeFeaturesOnly(originTest);
                    // Instances structuralAndCommentTesting = EvaluateModels.selectStructuralAndCommentFeaturesOnly(originTest);
                    // Instances changeAndCommentTesting = EvaluateModels.selectChangeAndCommentFeaturesOnly(originTest);
                    // Instances allModelTesting = EvaluateModels.selectAllFeatures(originTest);

                    for (Entry<String, Classifier> entry : classifiers.entrySet()) {
                        EvaluateModels.evaluateModel(entry.getValue(), productTraining, productTest, "productModel", entry.getKey());
                        EvaluateModels.evaluateModel(entry.getValue(), processTraining, processTest, "processModel", entry.getKey());
                        EvaluateModels.evaluateModel(entry.getValue(), productProcessTraining, productProcessTesting, "productProcessModel", entry.getKey());
                        EvaluateModels.evaluateModel(entry.getValue(), textualTraining, textualTest, "textualModel", entry.getKey());
                        EvaluateModels.evaluateModel(entry.getValue(), productProcessTextualTraining, productProcessTextualTestign, "productProcessTextualModel", entry.getKey());
                        EvaluateModels.evaluateModel(entry.getValue(), smellTraining, smellTest, "smellModel", entry.getKey());
                        EvaluateModels.evaluateModel(entry.getValue(), productProcessTextualSmellTraining, productProcessTextualSmellTesting, "productProcessTextualSmellModel", entry.getKey());
                        EvaluateModels.evaluateModel(entry.getValue(), devRelTraining, devRelTest, "devRelModel", entry.getKey());
                        EvaluateModels.evaluateModel(entry.getValue(), allTraining, allTesting, "allModel", entry.getKey());

                        // EvaluateModels.evaluateModel(entry.getValue(), onlyStructuralModelTraining, onlyStructuralModelTest, "structuralModel", entry.getKey());
                        // EvaluateModels.evaluateModel(entry.getValue(), onlyChangeModelTraining, onlyChangeModelTesting, "changeModel", entry.getKey());
                        // EvaluateModels.evaluateModel(entry.getValue(), onlyCommentModelTraining, onlyCommentModelTestign, "commentModel", entry.getKey());
                        // EvaluateModels.evaluateModel(entry.getValue(), structuralAndChangeModelTraining, structuralAndChangeModelTesting, "structuralAndChangeModel", entry.getKey());
                        // EvaluateModels.evaluateModel(entry.getValue(), structuralAndCommentTraining, structuralAndCommentTesting, "structuralAndCommentModel", entry.getKey());
                        // EvaluateModels.evaluateModel(entry.getValue(), changeAndCommentTraining, changeAndCommentTesting, "changeAndCommentModel", entry.getKey());
                        // EvaluateModels.evaluateModel(entry.getValue(), allModelTraining, allModelTesting, "allModel", entry.getKey());
                    }
                    // }
                }
            }

            // output = output.replaceAll("\\.", ",");
            FileUtilities.writeFile(output, basePath + "output/outputCleaned" + cleanedBy + ".csv");
            FileUtilities.writeFile(output10Fold, basePath + "output/output10FoldCleaned" + cleanedBy + ".csv");

            System.out.println("\n ******** Ended ******** \n");
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    static private Vector<String> readProjects(String filename) {
        Vector<String> list = new Vector<String>();
        try {
            Scanner s = new Scanner(new File(filename));
            while (s.hasNext()) {
                String project = s.next();
                if (!project.contains("//"))
                    list.add(project);
            }
            s.close();
        } catch (FileNotFoundException e) {
            System.out.println("The file " + filename + " does not exist.");
        }
        return list;
    }

    static private Vector<String> readReleases(String filename) {
        Vector<String> list = new Vector<String>();
        try {
            Scanner s = new Scanner(new File(filename));
            while (s.hasNext()) {
                String row = s.nextLine();
                List<String> elements = Arrays.asList(row.split(","));
                if (elements.size() > 0)
                    if (!elements.get(0).equals("0") && !elements.get(0).equals("ID"))
                        list.add(elements.get(0));
            }
            s.close();
        } catch (FileNotFoundException e) {
            System.out.println("The file " + filename + " does not exist.");
        }
        return list;
    }

    private static void evaluateModel10Fold(Classifier pClassifier, Instances pInstances, String pModelName, String pClassifierName) throws Exception {

        // other options
        int folds = 10;

        // randomize data
        Random rand = new Random(42);
        Instances randData = new Instances(pInstances);
        randData.randomize(rand);
        if (randData.classAttribute().isNominal())
            randData.stratify(folds);

        // perform cross-validation and add predictions
        Instances predictedData = null;
        Evaluation eval = new Evaluation(randData);

        int positiveValueIndexOfClassFeature = 0;
        for (int n = 0; n < folds; n++) {
            System.out.println(pClassifierName + " ==> " + pModelName + " Round: " + (n + 1) + "/" + folds);
            Instances train = randData.trainCV(folds, n);
            Instances test = randData.testCV(folds, n);
            // the above code is used by the StratifiedRemoveFolds filter, the
            // code below by the Explorer/Experimenter:
            // Instances train = randData.trainCV(folds, n, rand);

            int classFeatureIndex = 0;
            for (int i = 0; i < train.numAttributes(); i++) {
                if (train.attribute(i).name().equals("buggy")) {
                    classFeatureIndex = i;
                    break;
                }
            }

            Attribute classFeature = train.attribute(classFeatureIndex);
            for (int i = 0; i < classFeature.numValues(); i++) {
                if (classFeature.value(i).equals("TRUE")) {
                    positiveValueIndexOfClassFeature = i;
                }
            }

            train.setClassIndex(classFeatureIndex);
            test.setClassIndex(classFeatureIndex);

            // build and evaluate classifier
            pClassifier.buildClassifier(train);
            eval.evaluateModel(pClassifier, test);

            // add predictions
            AddClassification filter = new AddClassification();
            filter.setClassifier(pClassifier);
            filter.setOutputClassification(true);
            filter.setOutputDistribution(true);
            filter.setOutputErrorFlag(true);
            filter.setInputFormat(train);
            Filter.useFilter(train, filter);
            Instances pred = Filter.useFilter(test, filter);

            if (predictedData == null)
                predictedData = new Instances(pred, 0);

            for (int j = 0; j < pred.numInstances(); j++)
                predictedData.add(pred.instance(j));
        }

        double mcc = eval.matthewsCorrelationCoefficient(positiveValueIndexOfClassFeature);

        double accuracy = (eval.numTruePositives(positiveValueIndexOfClassFeature) + eval.numTrueNegatives(positiveValueIndexOfClassFeature)) / (eval.numTruePositives(positiveValueIndexOfClassFeature)
                + eval.numFalsePositives(positiveValueIndexOfClassFeature) + eval.numFalseNegatives(positiveValueIndexOfClassFeature) + eval.numTrueNegatives(positiveValueIndexOfClassFeature));

        double fmeasure = 2
                * ((eval.precision(positiveValueIndexOfClassFeature) * eval.recall(positiveValueIndexOfClassFeature)) / (eval.precision(positiveValueIndexOfClassFeature) + eval.recall(positiveValueIndexOfClassFeature)));

        EvaluateModels.output10Fold += EvaluateModels.projectName + "," + pClassifierName + "," + pModelName + "," + eval.numTruePositives(positiveValueIndexOfClassFeature) + ","
                + eval.numFalsePositives(positiveValueIndexOfClassFeature) + "," + eval.numFalseNegatives(positiveValueIndexOfClassFeature) + "," + eval.numTrueNegatives(positiveValueIndexOfClassFeature) + "," + accuracy
                + "," + eval.precision(positiveValueIndexOfClassFeature) + "," + eval.recall(positiveValueIndexOfClassFeature) + "," + fmeasure + "," + eval.areaUnderROC(positiveValueIndexOfClassFeature) + "," + mcc
                + ",";

        // for (int i = 0; i < textual.length; i++)
        // output += textual[i] + ",";
        output10Fold += "\n";
    }

    private static void evaluateModel(Classifier pClassifier, Instances pInstancesTraining, Instances pInstanceTesting, String pModelName, String pClassifierName) throws Exception {

        double textual[] = new double[8];

        /*
         * if (pModelName.equals("commentModel")) {// || pModelName.equals("structuralAndCommentModel") || pModelName.endsWith("changeAndCommentModel") || pModelName.equals("allModel")) { // InfoGain
         * AttributeSelection filter2 = new AttributeSelection(); InfoGainAttributeEval infoGain = new InfoGainAttributeEval(); Ranker ranker = new Ranker(); ranker.setNumToSelect(Math.min(500,
         * pInstancesTraining.numAttributes() - 1));
         * 
         * filter2.setEvaluator(infoGain); filter2.setSearch(ranker); filter2.SelectAttributes(pInstancesTraining);
         * 
         * // AttributeEvaluator as = new InfoGainAttributeEval(); double e1; for (int i = 0; i < pInstancesTraining.numAttributes() - 1; i++) { e1 = infoGain.evaluateAttribute(i); textual[i] = e1;
         * 
         * System.out.println(i + ") " + pInstancesTraining.attribute(i).name() + " => " + e1); // System.out.println(i + ", " + pInstancesTraining.attribute(i).toString() + e1); } System.out.println(); }
         */

        // double[][] ranked = filter2.rankedAttributes();
        // System.out.println("Number of attributes: " + pInstancesTraining.numAttributes());
        // for (int i = 0; i < ranked.length; i++) {
        // int index = (int) ranked[i][0];
        // double rank = ranked[i][1];
        //
        // // String classLabel = pInstancesTraining.classAttribute().value(index).trim();
        // String classLabel = pInstancesTraining.System.out.println(classLabel + " " + index + " => " + rank);
        // }

        // other options
        // int folds = 10;

        // randomize data
        // Random rand = new Random(42);
        // Instances randData = new Instances(pInstancesTraining);
        // randData.randomize(rand);
        // if (randData.classAttribute().isNominal())
        // randData.stratify(folds);

        // perform cross-validation and add predictions
        // Instances predictedData = null;
        Evaluation eval = new Evaluation(pInstancesTraining);

        int positiveValueIndexOfClassFeature = 0;
        // for (int n = 0; n < folds; n++) {
        // Instances train = randData.trainCV(folds, n);
        // Instances test = randData.testCV(folds, n);
        // // the above code is used by the StratifiedRemoveFolds filter, the
        // // code below by the Explorer/Experimenter:
        // // Instances train = randData.trainCV(folds, n, rand);
        //
        int classFeatureIndex = 0;
        for (int i = 0; i < pInstancesTraining.numAttributes(); i++) {
            if (pInstancesTraining.attribute(i).name().equals("buggy")) {
                classFeatureIndex = i;
                break;
            }
        }

        Attribute classFeature = pInstancesTraining.attribute(classFeatureIndex);
        for (int i = 0; i < classFeature.numValues(); i++) {
            if (classFeature.value(i).equals("TRUE")) {
                positiveValueIndexOfClassFeature = i;
            }
        }
        //
        // train.setClassIndex(classFeatureIndex);
        // test.setClassIndex(classFeatureIndex);

        AttributeSelectedClassifier classifier = new AttributeSelectedClassifier();
        CfsSubsetEval cfs = new CfsSubsetEval();
        GreedyStepwise search = new GreedyStepwise();
        search.setSearchBackwards(true);

        classifier.setClassifier(pClassifier);
        classifier.setEvaluator(cfs);
        classifier.setSearch(search);

        ClassBalancer filter = new ClassBalancer();
        filter.setInputFormat(pInstancesTraining);
        Instances balancedInstances = Filter.useFilter(pInstancesTraining, filter);

        // build and evaluate classifier
        classifier.buildClassifier(balancedInstances);
        eval.evaluateModel(classifier, pInstanceTesting);

        // add predictions

        // Instances pred = Filter.useFilter(pInstanceTesting, filter);
        //
        // if (predictedData == null)
        // predictedData = new Instances(pred, 0);
        //
        // for (int j = 0; j < pred.numInstances(); j++)
        // predictedData.add(pred.instance(j));
        // // }

        double mcc = eval.matthewsCorrelationCoefficient(positiveValueIndexOfClassFeature);

        double accuracy =

                (eval.numTruePositives(positiveValueIndexOfClassFeature) + eval.numTrueNegatives(positiveValueIndexOfClassFeature)) /

                        (eval.numTruePositives(positiveValueIndexOfClassFeature) + eval.numFalsePositives(positiveValueIndexOfClassFeature) + eval.numFalseNegatives(positiveValueIndexOfClassFeature)
                                + eval.numTrueNegatives(positiveValueIndexOfClassFeature));

        double fmeasure = 2
                * ((eval.precision(positiveValueIndexOfClassFeature) * eval.recall(positiveValueIndexOfClassFeature)) / (eval.precision(positiveValueIndexOfClassFeature) + eval.recall(positiveValueIndexOfClassFeature)));

        EvaluateModels.output += EvaluateModels.projectName + "," + pClassifierName + "," + pModelName + "," + eval.numTruePositives(positiveValueIndexOfClassFeature) + ","
                + eval.numFalsePositives(positiveValueIndexOfClassFeature) + "," + eval.numFalseNegatives(positiveValueIndexOfClassFeature) + "," + eval.numTrueNegatives(positiveValueIndexOfClassFeature) + "," + accuracy
                + "," + eval.precision(positiveValueIndexOfClassFeature) + "," + eval.recall(positiveValueIndexOfClassFeature) + "," + fmeasure + "," + eval.areaUnderROC(positiveValueIndexOfClassFeature) + "," + mcc
                + ",";

        // for (int i = 0; i < textual.length; i++)
        // output += textual[i] + ",";
        output += "\n";
    }

    private static Instances readFile(String pPath) throws Exception {
        ConverterUtils.DataSource source = new ConverterUtils.DataSource(pPath);
        // DataSource source = new DataSource(pPath);
        Instances data = source.getDataSet();
        // setting class attribute if the data format does not provide this information
        // For example, the XRFF format saves the class attribute information as well
        if (data.classIndex() == -1)
            data.setClassIndex(data.numAttributes() - 1);

        return data;
    }

    // private static Instances selectStructuralFeaturesOnly(Instances pOrigin) throws Exception {
    // // NB: It is an inverted process. To select indexes referring to structural
    // // metrics, you need to remove the indexes that refer to non-structural ones.
    // int[] nonStructuralIndexes = new int[] { 0, 1, 4, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33 };
    //
    // Remove remove = new Remove();
    // remove.setAttributeIndicesArray(nonStructuralIndexes);
    // remove.setInputFormat(pOrigin);
    // Instances newData = Filter.useFilter(pOrigin, remove);
    //
    // return newData;
    // }
    //
    // private static Instances selectCommentFeaturesOnly(Instances pOrigin) throws Exception {
    // // NB: It is an inverted process. To select indexes referring to structural
    // // metrics, you need to remove the indexes that refer to non-structural ones.
    // int[] nonStructuralIndexes = new int[] { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33 };
    //
    // Remove remove = new Remove();
    // remove.setAttributeIndicesArray(nonStructuralIndexes);
    // remove.setInputFormat(pOrigin);
    // Instances newData = Filter.useFilter(pOrigin, remove);
    //
    // return newData;
    // }
    //
    // private static Instances selectChangeFeaturesOnly(Instances pOrigin) throws Exception {
    // // NB: It is an inverted process. To select indexes referring to structural
    // // metrics, you need to remove the indexes that refer to non-structural ones.
    // int[] nonStructuralIndexes = new int[] { 0, 1, 4, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 };
    //
    // Remove remove = new Remove();
    // remove.setAttributeIndicesArray(nonStructuralIndexes);
    // remove.setInputFormat(pOrigin);
    // Instances newData = Filter.useFilter(pOrigin, remove);
    //
    // return newData;
    // }
    //
    // private static Instances selectStructuralAndChangeFeaturesOnly(Instances pOrigin) throws Exception {
    // // NB: It is an inverted process. To select indexes referring to structural
    // // metrics, you need to remove the indexes that refer to non-structural ones.
    // int[] nonStructuralIndexes = new int[] { 0, 1, 4, 11, 12, 13, 14, 15, 16, 17, 18 };
    //
    // Remove remove = new Remove();
    // remove.setAttributeIndicesArray(nonStructuralIndexes);
    // remove.setInputFormat(pOrigin);
    // Instances newData = Filter.useFilter(pOrigin, remove);
    //
    // return newData;
    // }
    //
    // private static Instances selectStructuralAndCommentFeaturesOnly(Instances pOrigin) throws Exception {
    // // NB: It is an inverted process. To select indexes referring to structural
    // // metrics, you need to remove the indexes that refer to non-structural ones.
    // int[] nonStructuralIndexes = new int[] { 0, 1, 4, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33 };
    //
    // Remove remove = new Remove();
    // remove.setAttributeIndicesArray(nonStructuralIndexes);
    // remove.setInputFormat(pOrigin);
    // Instances newData = Filter.useFilter(pOrigin, remove);
    //
    // return newData;
    // }
    //
    // private static Instances selectChangeAndCommentFeaturesOnly(Instances pOrigin) throws Exception {
    // // NB: It is an inverted process. To select indexes referring to structural
    // // metrics, you need to remove the indexes that refer to non-structural ones.
    // int[] nonStructuralIndexes = new int[] { 0, 1, 4, 2, 3, 5, 6, 7, 8, 9, 10 };
    //
    // Remove remove = new Remove();
    // remove.setAttributeIndicesArray(nonStructuralIndexes);
    // remove.setInputFormat(pOrigin);
    // Instances newData = Filter.useFilter(pOrigin, remove);
    //
    // return newData;
    // }

    private static Instances selectAllFeatures(Instances pOrigin) throws Exception {
        int[] nonHassanIndexes = new int[] { 0, 1, 4 };

        Remove remove = new Remove();
        remove.setAttributeIndicesArray(nonHassanIndexes);
        remove.setInputFormat(pOrigin);
        Instances newData = Filter.useFilter(pOrigin, remove);

        return newData;
    }

    private static Instances selectProductFeaturesOnly(Instances pOrigin) throws Exception {
        // NB: It is an inverted process. To select indexes referring to structural
        // metrics, you need to remove the indexes that refer to non-structural ones.
        int[] nonStructuralIndexes = new int[] { 0, 1, 4, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40 };

        Remove remove = new Remove();
        remove.setAttributeIndicesArray(nonStructuralIndexes);
        remove.setInputFormat(pOrigin);
        Instances newData = Filter.useFilter(pOrigin, remove);

        return newData;
    }

    private static Instances selectProcessFeaturesOnly(Instances pOrigin) throws Exception {
        // NB: It is an inverted process. To select indexes referring to structural
        // metrics, you need to remove the indexes that refer to non-structural ones.
        int[] nonStructuralIndexes = new int[] { 0, 1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 38, 39, 40 };

        Remove remove = new Remove();
        remove.setAttributeIndicesArray(nonStructuralIndexes);
        remove.setInputFormat(pOrigin);
        Instances newData = Filter.useFilter(pOrigin, remove);

        return newData;
    }

    private static Instances selectProductProcessFeaturesOnly(Instances pOrigin) throws Exception {
        // NB: It is an inverted process. To select indexes referring to structural
        // metrics, you need to remove the indexes that refer to non-structural ones.
        int[] nonStructuralIndexes = new int[] { 0, 1, 4, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 38, 39, 40 };

        Remove remove = new Remove();
        remove.setAttributeIndicesArray(nonStructuralIndexes);
        remove.setInputFormat(pOrigin);
        Instances newData = Filter.useFilter(pOrigin, remove);

        return newData;
    }

    private static Instances selectTextualFeaturesOnly(Instances pOrigin) throws Exception {
        // NB: It is an inverted process. To select indexes referring to structural
        // metrics, you need to remove the indexes that refer to non-structural ones.
        int[] nonStructuralIndexes = new int[] { 0, 1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40 };

        Remove remove = new Remove();
        remove.setAttributeIndicesArray(nonStructuralIndexes);
        remove.setInputFormat(pOrigin);
        Instances newData = Filter.useFilter(pOrigin, remove);

        return newData;
    }

    private static Instances selectProductProcessTextualFeaturesOnly(Instances pOrigin) throws Exception {
        // NB: It is an inverted process. To select indexes referring to structural
        // metrics, you need to remove the indexes that refer to non-structural ones.
        int[] nonStructuralIndexes = new int[] { 0, 1, 4, 19, 20, 21, 22, 38, 39, 40 };

        Remove remove = new Remove();
        remove.setAttributeIndicesArray(nonStructuralIndexes);
        remove.setInputFormat(pOrigin);
        Instances newData = Filter.useFilter(pOrigin, remove);

        return newData;
    }

    private static Instances selectSmellFeaturesOnly(Instances pOrigin) throws Exception {
        // NB: It is an inverted process. To select indexes referring to structural
        // metrics, you need to remove the indexes that refer to non-structural ones.
        int[] nonStructuralIndexes = new int[] { 0, 1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40 };

        Remove remove = new Remove();
        remove.setAttributeIndicesArray(nonStructuralIndexes);
        remove.setInputFormat(pOrigin);
        Instances newData = Filter.useFilter(pOrigin, remove);

        return newData;
    }

    private static Instances selectProductProcessTextualSmellFeaturesOnly(Instances pOrigin) throws Exception {
        // NB: It is an inverted process. To select indexes referring to structural
        // metrics, you need to remove the indexes that refer to non-structural ones.
        int[] nonStructuralIndexes = new int[] { 0, 1, 4, 38, 39, 40 };

        Remove remove = new Remove();
        remove.setAttributeIndicesArray(nonStructuralIndexes);
        remove.setInputFormat(pOrigin);
        Instances newData = Filter.useFilter(pOrigin, remove);

        return newData;
    }

    private static Instances selectDevRelFeaturesOnly(Instances pOrigin) throws Exception {
        // NB: It is an inverted process. To select indexes referring to structural
        // metrics, you need to remove the indexes that refer to non-structural ones.
        int[] nonStructuralIndexes = new int[] { 0, 1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37 };

        Remove remove = new Remove();
        remove.setAttributeIndicesArray(nonStructuralIndexes);
        remove.setInputFormat(pOrigin);
        Instances newData = Filter.useFilter(pOrigin, remove);

        return newData;
    }
}
